"""Business logic for applications."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.codes import generate_prx_code
from app.core.exceptions import (
    ApplicationAccessForbiddenError,
    ApplicationNotFoundError,
    ClaimNotFoundError,
    InvalidStatusTransitionError,
    ServiceNotFoundError,
    ValidationError,
)
from app.core.jobs import JobQueueManager
from app.core.security import generate_id
from app.modules.applications.constants import (
    CLIENT_CANCELLABLE,
    SYSTEM_MESSAGES,
    VALID_STATUS_TRANSITIONS,
)
from app.modules.applications.models import Application
from app.modules.applications.repository import ApplicationsRepository
from app.modules.applications.schemas import (
    AdminApplicationListResponse,
    AgentCaseListResponse,
    AgentCaseSummary,
    AnalyticsResponse,
    ApplicationDetailResponse,
    ApplicationListResponse,
    ApplicationLookupData,
    ApplicationSummaryResponse,
    CancelApplicationRequest,
    StatusHistoryResponse,
    SubmitApplicationRequest,
    SubmitApplicationResponse,
    TrackerResponse,
    UpdateStatusRequest,
)
from app.modules.auth.repository import AuthRepository
from app.modules.documents.repository import DocumentsRepository
from app.modules.documents.schemas import DocumentResponse
from app.modules.messages.repository import MessagesRepository
from app.modules.messages.schemas import MessageResponse
from app.modules.messages.service import MessagesService
from app.modules.services.constants import PRICING_TIERS
from app.modules.services.repository import ServicesRepository


class ApplicationsService:
    def __init__(
        self,
        session: AsyncSession,
        job_queue: JobQueueManager | None = None,
    ) -> None:
        self.session = session
        self.job_queue = job_queue
        self.repo = ApplicationsRepository(session)
        self.services_repo = ServicesRepository(session)
        self.auth_repo = AuthRepository(session)
        self.docs_repo = DocumentsRepository(session)
        self.messages_repo = MessagesRepository(session)
        self.messages_service = MessagesService(session, job_queue)

    async def submit_application(
        self,
        *,
        client_id: str,
        payload: SubmitApplicationRequest,
        submission_ip: str | None = None,
    ) -> SubmitApplicationResponse:
        service = await self.services_repo.get_by_slug(payload.service_slug, load_nested=True)
        if service is None or service.status != "active":
            raise ServiceNotFoundError()
        if payload.tier not in PRICING_TIERS:
            raise ValidationError(message="Invalid pricing tier.", fields=["tier"])
        tier = next((t for t in service.pricing_tiers if t.tier == payload.tier), None)
        if tier is None or not tier.is_available:
            raise ValidationError(message="Selected tier is not available.", fields=["tier"])
        self._validate_service_data(service.form_fields, payload.service_data)
        code = await self._generate_unique_code()
        now = datetime.now(UTC)
        app = await self.repo.create_application(
            application_id=generate_id("app"),
            code=code,
            service_id=service.service_id,
            service_slug=service.slug,
            service_name=service.name,
            tier=payload.tier,
            status="received",
            client_id=client_id,
            personal_info=payload.personal_info.model_dump(),
            service_data=payload.service_data,
            payment_status="pending",
            payment_amount=tier.platform_fee + tier.government_fee,
            submission_ip=submission_ip,
            submitted_at=now,
        )
        await self.repo.add_status_history(
            id=generate_id("ash"),
            application_id=app.application_id,
            status="received",
            changed_by=client_id,
            changed_by_role="client",
            note="Application submitted",
        )
        await self.messages_service.create_system_message(
            application_id=app.application_id,
            content="Your application has been received and is awaiting assignment to an agent.",
        )
        await self.session.commit()
        if self.job_queue:
            client = await self.auth_repo.get_user_by_id(client_id)
            if client and client.email:
                await self.job_queue.enqueue(
                    "send_email_job",
                    to=client.email,
                    subject=f"Application Submitted — {service.name}",
                    body=(
                        f"Your application has been submitted.\n\n"
                        f"Tracking code: {code}\n"
                        f"Service: {service.name}\n"
                        f"Tier: {payload.tier}\n"
                        f"Estimated turnaround: {tier.eta_business_days} business days"
                    ),
                )
        return SubmitApplicationResponse(
            application_id=app.application_id,
            code=code,
            service_name=service.name,
            tier=payload.tier,
            payment_required=tier.platform_fee + tier.government_fee > 0,
        )

    async def list_client_applications(self, client_id: str) -> ApplicationListResponse:
        apps = await self.repo.list_by_client(client_id)
        return ApplicationListResponse(
            applications=[self._summary(a) for a in apps]
        )

    async def get_client_application(
        self,
        *,
        code: str,
        client_id: str,
    ) -> ApplicationDetailResponse:
        app = await self._get_owned(code, client_id)
        return await self._detail(app, include_internal_messages=False)

    async def cancel_application(
        self,
        *,
        code: str,
        client_id: str,
        payload: CancelApplicationRequest,
    ) -> None:
        app = await self._get_owned(code, client_id)
        if app.status not in CLIENT_CANCELLABLE:
            raise InvalidStatusTransitionError(
                current_status=app.status,
                valid_next_statuses=sorted(CLIENT_CANCELLABLE),
            )
        app.cancellation_reason = payload.reason
        await self.transition_status(
            code=code,
            payload=UpdateStatusRequest(status="cancelled", note=payload.reason),
            user_id=client_id,
            user_role="client",
            force=False,
        )

    async def transition_status(
        self,
        *,
        code: str,
        payload: UpdateStatusRequest,
        user_id: str,
        user_role: str,
        force: bool = False,
    ) -> ApplicationDetailResponse:
        app = await self.repo.get_by_code(code, load_history=True)
        if app is None:
            raise ApplicationNotFoundError()
        if not force:
            if user_role == "client" and app.client_id != user_id:
                raise ApplicationAccessForbiddenError(code=code)
            if user_role == "staff:agent" and app.assigned_agent_id != user_id:
                raise ApplicationAccessForbiddenError(code=code)
            allowed = VALID_STATUS_TRANSITIONS.get(app.status, set())
            if payload.status not in allowed:
                raise InvalidStatusTransitionError(
                    current_status=app.status,
                    valid_next_statuses=sorted(allowed),
                )
        if payload.rejection_reason:
            app.rejection_reason = payload.rejection_reason
        await self._apply_status_change(
            app=app,
            new_status=payload.status,
            changed_by=user_id,
            changed_by_role=user_role,
            note=payload.note,
        )
        await self.session.commit()
        await self._send_status_email(app, payload.status)
        return await self._detail(app, include_internal_messages=user_role.startswith("staff"))

    async def list_agent_cases(self, agent_id: str) -> AgentCaseListResponse:
        apps = await self.repo.list_by_agent(agent_id)
        cases = []
        for app in apps:
            client = await self.auth_repo.get_user_by_id(app.client_id)
            unread = await self.messages_repo.count_unread_for_client(app.application_id)
            cases.append(
                AgentCaseSummary(
                    code=app.code,
                    service_name=app.service_name,
                    client_name=client.name if client else "Unknown",
                    status=app.status,
                    tier=app.tier,
                    submitted_at=app.submitted_at,
                    sla_state=self._sla_state(app),
                    unread_messages=unread,
                )
            )
        return AgentCaseListResponse(cases=cases)

    async def get_agent_case(self, *, code: str, agent_id: str) -> ApplicationDetailResponse:
        app = await self.repo.get_by_code(code, load_history=True)
        if app is None:
            raise ApplicationNotFoundError()
        if app.assigned_agent_id != agent_id:
            raise ApplicationAccessForbiddenError(code=code)
        return await self._detail(app, include_internal_messages=True)

    async def get_admin_application(self, code: str) -> ApplicationDetailResponse:
        app = await self.repo.get_by_code(code, load_history=True)
        if app is None:
            raise ApplicationNotFoundError()
        return await self._detail(app, include_internal_messages=True)

    async def list_admin_applications(
        self,
        *,
        status: str | None = None,
        service_id: str | None = None,
        agent_id: str | None = None,
        tier: str | None = None,
        payment_status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> AdminApplicationListResponse:
        apps, total = await self.repo.list_all(
            status=status,
            service_id=service_id,
            agent_id=agent_id,
            tier=tier,
            payment_status=payment_status,
            offset=offset,
            limit=limit,
        )
        return AdminApplicationListResponse(
            applications=[self._summary(a) for a in apps],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def get_tracker(self, code: str) -> TrackerResponse:
        app = await self.repo.get_by_code(code)
        if app is None:
            raise ApplicationNotFoundError()
        service = await self.services_repo.get_by_id(app.service_id, load_nested=True)
        current_step_number = None
        current_step_title = None
        estimated_completion = None
        if service:
            steps = sorted(service.steps, key=lambda s: s.step_number)
            if steps:
                idx = min(len(steps) - 1, max(0, _status_to_step_index(app.status)))
                current_step_number = steps[idx].step_number
                current_step_title = steps[idx].title
            tier = next((t for t in service.pricing_tiers if t.tier == app.tier), None)
            if tier:
                eta = app.submitted_at + timedelta(days=tier.eta_business_days)
                estimated_completion = eta.isoformat()
        return TrackerResponse(
            code=app.code,
            service_name=app.service_name,
            status=app.status,
            current_step_number=current_step_number,
            current_step_title=current_step_title,
            estimated_completion=estimated_completion,
            submitted_at=app.submitted_at,
            updated_at=app.updated_at,
        )

    async def lookup_by_code(self, code: str) -> ApplicationLookupData:
        app = await self.repo.get_by_code(code)
        if app is None:
            raise ClaimNotFoundError()
        return ApplicationLookupData(
            code=app.code,
            serviceName=app.service_name,
            submittedDate=app.submitted_at.isoformat(),
            status=app.status,
        )

    async def claim(self, *, code: str, phone: str, client_id: str) -> None:
        app = await self.repo.get_by_code(code)
        if app is None:
            raise ClaimNotFoundError()
        personal_phone = str(app.personal_info.get("phone", ""))
        if personal_phone and phone not in personal_phone:
            raise ClaimNotFoundError()
        if app.client_id != client_id:
            app.client_id = client_id
            await self.session.commit()

    async def get_analytics(self) -> AnalyticsResponse:
        by_status = await self.repo.count_by_status()
        by_service_raw = await self.repo.count_by_service()
        by_service = [
            {"service_name": name, "service_id": sid, "count": count}
            for name, sid, count in by_service_raw
        ]
        total = sum(by_status.values())
        completed = by_status.get("completed", 0)
        sla_rate = (completed / total * 100) if total else 0.0
        pending_payment = by_status.get("received", 0)
        return AnalyticsResponse(
            by_status=by_status,
            by_service=by_service,
            total_applications=total,
            sla_compliance_rate=round(sla_rate, 2),
            payment_pending_count=pending_payment,
        )

    async def _apply_status_change(
        self,
        *,
        app: Application,
        new_status: str,
        changed_by: str,
        changed_by_role: str,
        note: str | None,
    ) -> None:
        app.status = new_status
        now = datetime.now(UTC)
        if new_status == "completed":
            app.completed_at = now
        elif new_status == "rejected":
            app.rejected_at = now
        elif new_status == "cancelled":
            app.cancelled_at = now
        await self.repo.add_status_history(
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

    async def _detail(
        self,
        app: Application,
        *,
        include_internal_messages: bool,
    ) -> ApplicationDetailResponse:
        if include_internal_messages:
            messages = await self.messages_repo.list_for_staff(app.application_id)
        else:
            messages = await self.messages_repo.list_for_client(app.application_id)
        docs = await self.docs_repo.list_by_application(app.application_id)
        history = app.status_history if hasattr(app, "status_history") else []
        if not history:
            app_loaded = await self.repo.get_by_code(app.code, load_history=True)
            history = app_loaded.status_history if app_loaded else []
        return ApplicationDetailResponse(
            application_id=app.application_id,
            code=app.code,
            service_name=app.service_name,
            service_slug=app.service_slug,
            tier=app.tier,
            status=app.status,
            personal_info=app.personal_info,
            service_data=app.service_data,
            payment_status=app.payment_status,
            payment_amount=app.payment_amount,
            submitted_at=app.submitted_at,
            assigned_agent_id=app.assigned_agent_id,
            status_history=[
                StatusHistoryResponse.model_validate(h) for h in history
            ],
            documents=[DocumentResponse.model_validate(d) for d in docs],
            messages=[MessageResponse.model_validate(m) for m in messages],
        )

    async def _get_owned(self, code: str, client_id: str) -> Application:
        app = await self.repo.get_by_code(code, load_history=True)
        if app is None:
            raise ApplicationNotFoundError()
        if app.client_id != client_id:
            raise ApplicationAccessForbiddenError(code=code)
        return app

    async def _generate_unique_code(self) -> str:
        for _ in range(10):
            code = generate_prx_code()
            if not await self.repo.code_exists(code):
                return code
        raise RuntimeError("Failed to generate unique PRX code")

    def _validate_service_data(self, form_fields, service_data: dict[str, object]) -> None:
        missing = []
        for field in form_fields:
            if field.conditional_on_field:
                cond_val = service_data.get(field.conditional_on_field)
                if str(cond_val) != field.conditional_on_value:
                    continue
            if field.is_required and field.field_key not in service_data:
                missing.append(field.field_key)
        if missing:
            raise ValidationError(
                message="Missing required service fields.",
                fields=missing,
            )

    def _summary(self, app: Application) -> ApplicationSummaryResponse:
        return ApplicationSummaryResponse(
            application_id=app.application_id,
            code=app.code,
            service_name=app.service_name,
            service_slug=app.service_slug,
            status=app.status,
            tier=app.tier,
            submitted_at=app.submitted_at,
            payment_status=app.payment_status,
        )

    def _sla_state(self, app: Application) -> str:
        if app.status in {"completed", "rejected", "cancelled"}:
            return "ok"
        days = (datetime.now(UTC) - app.submitted_at).days
        if days > 14:
            return "over"
        if days > 10:
            return "warn"
        return "ok"

    async def _send_status_email(self, app: Application, status: str) -> None:
        if not self.job_queue:
            return
        client = await self.auth_repo.get_user_by_id(app.client_id)
        if not client or not client.email:
            return
        subjects = {
            "under_review": f"Your application is being reviewed — {app.code}",
            "awaiting_client": f"Action Required — {app.code}",
            "completed": f"Your application is complete — {app.code}",
            "rejected": f"Application Update — {app.code}",
        }
        subject = subjects.get(status)
        if subject:
            body = SYSTEM_MESSAGES.get(status, f"Your application status is now: {status}")
            await self.job_queue.enqueue(
                "send_email_job",
                to=client.email,
                subject=subject,
                body=body,
            )


def _status_to_step_index(status: str) -> int:
    mapping = {
        "received": 0,
        "under_review": 1,
        "in_progress": 2,
        "awaiting_client": 2,
        "submitted_to_authority": 3,
        "awaiting_response": 4,
        "completed": 4,
        "rejected": 4,
        "cancelled": 0,
    }
    return mapping.get(status, 0)
