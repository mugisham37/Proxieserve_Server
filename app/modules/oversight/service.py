"""Oversight board business logic."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApplicationNotFoundError
from app.core.security import generate_id
from app.modules.applications.constants import TERMINAL_STATUSES
from app.modules.applications.models import Application
from app.modules.applications.repository import ApplicationsRepository
from app.modules.auth.repository import AuthRepository
from app.modules.documents.models import ApplicationDocument
from app.modules.oversight.models import ApplicationEscalation
from app.modules.oversight.repository import OversightRepository
from app.modules.oversight.schemas import (
    EscalateCaseRequest,
    OversightCaseListResponse,
    OversightCaseResponse,
    ResolveCaseRequest,
)


class OversightService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = OversightRepository(session)
        self.apps_repo = ApplicationsRepository(session)
        self.auth_repo = AuthRepository(session)

    async def list_cases(self, *, tab: str) -> OversightCaseListResponse:
        now = datetime.now(UTC)
        apps = list(
            await self.session.scalars(
                select(Application).where(~Application.status.in_(TERMINAL_STATUSES))
            )
        )
        escalation_rows = list(
            await self.session.scalars(
                select(ApplicationEscalation).where(
                    ApplicationEscalation.oversight_status == "escalated"
                )
            )
        )
        app_id_to_escalation = {e.application_id: e for e in escalation_rows}
        escalated_ids = set(app_id_to_escalation.keys())

        fail_docs = list(
            await self.session.scalars(
                select(ApplicationDocument).where(ApplicationDocument.qc_status == "fail")
            )
        )
        doc_fail_app_ids = {d.application_id for d in fail_docs}

        cases: list[OversightCaseResponse] = []
        seen: set[str] = set()

        for app in apps:
            sla_breach = (
                app.sla_deadline is not None
                and now > app.sla_deadline
            )
            disputed = app.application_id in escalated_ids
            doc_fail = app.application_id in doc_fail_app_ids
            if not (sla_breach or disputed or doc_fail):
                continue
            if app.code in seen:
                continue
            seen.add(app.code)
            case = await self._build_case(
                app,
                sla_breach=sla_breach,
                disputed=disputed,
                doc_fail=doc_fail,
                escalation=app_id_to_escalation.get(app.application_id),
                now=now,
            )
            if tab == "sla" and not sla_breach:
                continue
            if tab == "disputes" and not disputed:
                continue
            if tab == "attention" and not (sla_breach or disputed or doc_fail):
                continue
            cases.append(case)
        return OversightCaseListResponse(cases=cases)

    async def _build_case(
        self,
        app: Application,
        *,
        sla_breach: bool,
        disputed: bool,
        doc_fail: bool,
        escalation: ApplicationEscalation | None,
        now: datetime,
    ) -> OversightCaseResponse:
        agent_name = "Unassigned"
        if app.assigned_agent_id:
            agent = await self.auth_repo.get_user_by_id(app.assigned_agent_id)
            agent_name = agent.name if agent else "Unknown"
        client_name = str(app.personal_info.get("fullName", "Unknown"))
        if disputed and escalation:
            status = "escalated"
            issue = escalation.reason
        elif sla_breach:
            status = "sla-breach"
            days = (now - app.sla_deadline).days if app.sla_deadline else 0
            issue = f"SLA deadline passed {days} day(s) ago"
        elif doc_fail:
            status = "in-progress"
            issue = "Document quality check failed"
        else:
            status = "in-progress"
            issue = None
        return OversightCaseResponse(
            code=app.code,
            service=app.service_name,
            agent=agent_name,
            client=client_name,
            status=status,
            issue=issue,
        )

    async def escalate_case(
        self,
        *,
        code: str,
        admin_id: str,
        payload: EscalateCaseRequest,
    ) -> None:
        app = await self.apps_repo.get_by_code(code)
        if app is None:
            raise ApplicationNotFoundError()
        await self.repo.create_escalation(
            id=generate_id("esc"),
            application_id=app.application_id,
            escalated_by=admin_id,
            reason=payload.reason,
            oversight_status="escalated",
            created_at=datetime.now(UTC),
        )
        await self.session.commit()

    async def resolve_case(
        self,
        *,
        code: str,
        admin_id: str,
        payload: ResolveCaseRequest,
    ) -> None:
        app = await self.apps_repo.get_by_code(code)
        if app is None:
            raise ApplicationNotFoundError()
        escalation = await self.repo.get_active_escalation(app.application_id)
        if escalation is None:
            raise ApplicationNotFoundError()
        escalation.oversight_status = "resolved"
        escalation.resolved_at = datetime.now(UTC)
        escalation.resolved_by = admin_id
        escalation.resolution_note = payload.resolution_note
        await self.session.commit()
