"""Business logic for agent assignment."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AgentNotAvailableError,
    AgentNotFoundError,
    ApplicationAlreadyAssignedError,
    ApplicationNotFoundError,
    DailyCapExceededError,
)
from app.core.jobs import JobQueueManager
from app.core.security import generate_id
from app.modules.applications.constants import SYSTEM_MESSAGES, VALID_STATUS_TRANSITIONS
from app.modules.applications.repository import ApplicationsRepository
from app.modules.assignments.repository import AssignmentsRepository
from app.modules.assignments.schemas import (
    AgentSettingsResponse,
    AssignAgentRequest,
    UnassignedCaseResponse,
    UnassignedQueueResponse,
    UpdateAgentSettingsRequest,
)
from app.modules.auth.repository import AuthRepository
from app.modules.messages.service import MessagesService
from app.modules.services.repository import ServicesRepository


class AssignmentsService:
    def __init__(
        self,
        session: AsyncSession,
        job_queue: JobQueueManager | None = None,
    ) -> None:
        self.session = session
        self.job_queue = job_queue
        self.repo = AssignmentsRepository(session)
        self.apps_repo = ApplicationsRepository(session)
        self.auth_repo = AuthRepository(session)
        self.services_repo = ServicesRepository(session)
        self.messages_service = MessagesService(session, job_queue)

    async def _apply_status_change(
        self,
        *,
        app,
        new_status: str,
        changed_by: str,
        changed_by_role: str,
        note: str | None,
    ) -> None:
        allowed = VALID_STATUS_TRANSITIONS.get(app.status, set())
        if new_status not in allowed and new_status != app.status:
            from app.core.exceptions import InvalidStatusTransitionError

            raise InvalidStatusTransitionError(
                current_status=app.status,
                valid_next_statuses=sorted(allowed),
            )
        app.status = new_status
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        if new_status == "completed":
            app.completed_at = now
        elif new_status == "rejected":
            app.rejected_at = now
        elif new_status == "cancelled":
            app.cancelled_at = now
        await self.apps_repo.add_status_history(
            id=generate_id("ash"),
            application_id=app.application_id,
            status=new_status,
            changed_by=changed_by,
            changed_by_role=changed_by_role,
            note=note,
        )
        content = SYSTEM_MESSAGES.get(new_status)
        if content:
            await self.messages_service.create_system_message(
                application_id=app.application_id,
                content=content,
            )

    async def assign_by_admin(
        self,
        *,
        code: str,
        admin_id: str,
        payload: AssignAgentRequest,
    ) -> None:
        app = await self.apps_repo.get_by_code(code)
        if app is None:
            raise ApplicationNotFoundError()
        agent = await self.auth_repo.get_user_by_id(payload.agent_id)
        if agent is None or agent.role != "staff:agent" or not agent.is_active:
            raise AgentNotFoundError()
        await self._validate_agent_available(payload.agent_id)
        previous_agent_id = app.assigned_agent_id
        app.assigned_agent_id = payload.agent_id
        from datetime import UTC, datetime

        app.assigned_at = datetime.now(UTC)
        await self.apps_repo.add_assignment_history(
            id=generate_id("aah"),
            application_id=app.application_id,
            previous_agent_id=previous_agent_id,
            new_agent_id=payload.agent_id,
            performed_by=admin_id,
            performed_by_role="staff:admin",
            note=payload.note,
        )
        if app.status == "received":
            await self._apply_status_change(
                app=app,
                new_status="under_review",
                changed_by=admin_id,
                changed_by_role="staff:admin",
                note=payload.note,
            )
        await self.session.commit()
        await self._send_assignment_emails(app, agent, previous_agent_id)

    async def claim_unassigned(
        self,
        *,
        code: str,
        agent_id: str,
    ) -> None:
        await self._validate_agent_available(agent_id)
        app = await self.apps_repo.get_for_update(code)
        if app is None:
            raise ApplicationAlreadyAssignedError()
        if app.assigned_agent_id is not None:
            raise ApplicationAlreadyAssignedError()
        if app.status != "received":
            raise ApplicationNotFoundError()
        from datetime import UTC, datetime

        app.assigned_agent_id = agent_id
        app.assigned_at = datetime.now(UTC)
        await self.apps_repo.add_assignment_history(
            id=generate_id("aah"),
            application_id=app.application_id,
            previous_agent_id=None,
            new_agent_id=agent_id,
            performed_by=agent_id,
            performed_by_role="staff:agent",
            note="Claimed from unassigned queue",
        )
        await self._apply_status_change(
            app=app,
            new_status="under_review",
            changed_by=agent_id,
            changed_by_role="staff:agent",
            note="Claimed from unassigned queue",
        )
        await self.session.commit()
        agent = await self.auth_repo.get_user_by_id(agent_id)
        if agent:
            await self._send_assignment_emails(app, agent, None)

    async def list_unassigned_queue(self) -> UnassignedQueueResponse:
        apps = await self.apps_repo.list_unassigned()
        cases = []
        for app in apps:
            eta = None
            service = await self.services_repo.get_by_id(app.service_id, load_nested=True)
            if service:
                tier = next((t for t in service.pricing_tiers if t.tier == app.tier), None)
                if tier:
                    eta = tier.eta_business_days
            cases.append(
                UnassignedCaseResponse(
                    code=app.code,
                    service_name=app.service_name,
                    submitted_at=app.submitted_at.isoformat(),
                    tier=app.tier,
                    eta_business_days=eta,
                )
            )
        return UnassignedQueueResponse(count=len(cases), cases=cases)

    async def get_agent_settings(self, agent_id: str) -> AgentSettingsResponse:
        settings = await self.repo.get_or_create_settings(agent_id)
        await self.session.commit()
        return AgentSettingsResponse.model_validate(settings)

    async def update_agent_settings(
        self,
        agent_id: str,
        payload: UpdateAgentSettingsRequest,
    ) -> AgentSettingsResponse:
        settings = await self.repo.get_or_create_settings(agent_id)
        await self.repo.update_settings(
            settings,
            **payload.model_dump(exclude_unset=True),
        )
        await self.session.commit()
        return AgentSettingsResponse.model_validate(settings)

    async def _validate_agent_available(self, agent_id: str) -> None:
        settings = await self.repo.get_or_create_settings(agent_id)
        if not settings.accepting_cases:
            raise AgentNotAvailableError()
        if settings.daily_case_cap is not None:
            count = await self.apps_repo.count_agent_assignments_today(agent_id)
            if count >= settings.daily_case_cap:
                raise DailyCapExceededError(cap=settings.daily_case_cap)

    async def _send_assignment_emails(
        self,
        app,
        agent,
        previous_agent_id: str | None,
    ) -> None:
        if not self.job_queue:
            return
        if agent.email:
            await self.job_queue.enqueue(
                "send_email_job",
                to=agent.email,
                subject=f"New Case Assigned — {app.code}",
                body=f"You have been assigned case {app.code} for {app.service_name}.",
            )
        if previous_agent_id:
            prev = await self.auth_repo.get_user_by_id(previous_agent_id)
            if prev and prev.email:
                await self.job_queue.enqueue(
                    "send_email_job",
                    to=prev.email,
                    subject=f"Case Reassigned — {app.code}",
                    body=f"Case {app.code} has been reassigned to another agent.",
                )
        client = await self.auth_repo.get_user_by_id(app.client_id)
        if client and client.email:
            await self.job_queue.enqueue(
                "send_email_job",
                to=client.email,
                subject=f"Your application is being reviewed — {app.code}",
                body=SYSTEM_MESSAGES["under_review"],
            )
