"""Business logic for agent assignment."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AgentNotAvailableError,
    AgentNotFoundError,
    ApplicationAlreadyAssignedError,
    ApplicationNotFoundError,
    DailyCapExceededError,
    InvalidServiceCategoryError,
)
from app.modules.applications.constants import SERVICE_CATEGORIES, SYSTEM_MESSAGES, VALID_STATUS_TRANSITIONS
from app.modules.applications.models import Application
from app.modules.applications.repository import ApplicationsRepository
from app.modules.assignments.repository import AssignmentsRepository
from app.modules.assignments.schemas import (
    AgentMetricsResponse,
    AgentSettingsResponse,
    AgentSkillItem,
    AgentSkillsResponse,
    AssignAgentRequest,
    LeaderboardEntryResponse,
    LeaderboardResponse,
    SetAgentSkillsRequest,
    UnassignedCaseResponse,
    UnassignedQueueResponse,
    UpdateAgentSettingsRequest,
    WeeklyBarResponse,
)
from app.core.jobs import JobQueueManager
from app.core.security import generate_id
from app.modules.audit.service import write_audit_entry
from app.modules.auth.repository import AuthRepository
from app.modules.messages.service import MessagesService
from app.modules.services.repository import ServicesRepository

MIN_ASSIGNMENT_SCORE = 15.0
SOFT_CAP = 20


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

    async def do_assign(
        self,
        *,
        app: Application,
        agent_id: str,
        performed_by: str,
        performed_by_role: str,
        note: str | None,
        ip_address: str | None = None,
    ) -> None:
        previous_agent_id = app.assigned_agent_id
        app.assigned_agent_id = agent_id
        app.assigned_at = datetime.now(UTC)
        await self.apps_repo.add_assignment_history(
            id=generate_id("aah"),
            application_id=app.application_id,
            previous_agent_id=previous_agent_id,
            new_agent_id=agent_id,
            performed_by=performed_by,
            performed_by_role=performed_by_role,
            note=note,
        )
        if app.status == "received":
            await self._apply_status_change(
                app=app,
                new_status="under_review",
                changed_by=performed_by,
                changed_by_role=performed_by_role,
                note=note,
            )
        await write_audit_entry(
            self.session,
            actor_id=performed_by if performed_by_role != "system" else None,
            actor_role=performed_by_role if performed_by_role != "system" else None,
            action="agent.assigned",
            resource_type="application",
            resource_id=app.code,
            details={"agent_id": agent_id, "previous_agent_id": previous_agent_id},
            ip_address=ip_address,
            kind="Assignment",
        )

    async def assign_by_admin(
        self,
        *,
        code: str,
        admin_id: str,
        payload: AssignAgentRequest,
        ip_address: str | None = None,
    ) -> None:
        app = await self.apps_repo.get_by_code(code)
        if app is None:
            raise ApplicationNotFoundError()
        agent = await self.auth_repo.get_user_by_id(payload.agent_id)
        if agent is None or agent.role != "staff:agent" or not agent.is_active:
            raise AgentNotFoundError()
        await self._validate_agent_available(payload.agent_id)
        previous_agent_id = app.assigned_agent_id
        await self.do_assign(
            app=app,
            agent_id=payload.agent_id,
            performed_by=admin_id,
            performed_by_role="staff:admin",
            note=payload.note,
            ip_address=ip_address,
        )
        await self.session.commit()
        await self.send_assignment_emails(app, agent, previous_agent_id)

    async def auto_assign_by_admin(self, *, code: str) -> bool:
        app = await self.apps_repo.get_by_code(code)
        if app is None:
            raise ApplicationNotFoundError()
        winner_id, score = await self.score_agents(app)
        if winner_id is None:
            await self.notify_no_agent_available(app, score)
            await self.session.commit()
            return False
        await self.do_assign(
            app=app,
            agent_id=winner_id,
            performed_by=winner_id,
            performed_by_role="system",
            note="Manual re-run of auto-assignment",
        )
        await self.session.commit()
        agent = await self.auth_repo.get_user_by_id(winner_id)
        if agent:
            await self.send_assignment_emails(app, agent, None)
        return True

    async def score_agents(self, application: Application) -> tuple[str | None, float]:
        service = await self.services_repo.get_by_id(application.service_id)
        category = service.category if service else "other"
        eligible = await self.repo.fetch_eligible_agents_data()
        if not eligible:
            return None, 0.0
        agent_ids = [str(a["user_id"]) for a in eligible]
        skills_map = await self.repo.fetch_skills_for_agents(agent_ids)
        sla_rates = await self.repo.fetch_sla_compliance_rates(agent_ids)
        scores: list[tuple[str, float, datetime | None]] = []
        for agent in eligible:
            agent_id = str(agent["user_id"])
            active = int(agent["active_count"])
            cap = agent["daily_case_cap"] or SOFT_CAP
            skill_rows = skills_map.get(agent_id, [])
            match = next((s for s in skill_rows if s.service_category == category), None)
            if match:
                expertise = (match.proficiency_level / 5.0) * 100.0
            else:
                expertise = 25.0
            expertise_pts = expertise * 0.40
            workload_ratio = min(1.0, active / float(cap))
            workload = max(0.0, 100.0 - workload_ratio * 100.0)
            workload_pts = workload * 0.30
            sla_rate = sla_rates.get(agent_id, 50.0)
            sla_pts = sla_rate * 0.20
            if application.tier == "urgent":
                urgency_pts = sla_rate * 0.10
            elif application.tier == "express" and sla_rate > 80.0:
                urgency_pts = 10.0
            else:
                urgency_pts = 10.0
            total = expertise_pts + workload_pts + sla_pts + urgency_pts
            last_at = agent.get("last_assigned_at")
            scores.append((agent_id, total, last_at if isinstance(last_at, datetime) else None))
        scores.sort(key=lambda x: (-x[1], x[2] or datetime.min.replace(tzinfo=UTC)))
        if not scores or scores[0][1] < MIN_ASSIGNMENT_SCORE:
            return None, scores[0][1] if scores else 0.0
        return scores[0][0], scores[0][1]

    async def notify_no_agent_available(self, app: Application, score: float) -> None:
        if not self.job_queue:
            return
        from app.modules.auth.models import User
        from sqlalchemy import select

        admins = list(
            await self.session.scalars(select(User).where(User.role == "staff:admin"))
        )
        reason = "no eligible agents" if score == 0 else f"all scores below threshold (best={score:.1f})"
        for admin in admins:
            if admin.email:
                await self.job_queue.enqueue(
                    "send_email_job",
                    to=admin.email,
                    subject=f"Unassigned Application — {app.code}",
                    body=(
                        f"Application {app.code} could not be auto-assigned.\n"
                        f"Reason: {reason}\n"
                        f"Service: {app.service_name}"
                    ),
                )

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
        await self.do_assign(
            app=app,
            agent_id=agent_id,
            performed_by=agent_id,
            performed_by_role="staff:agent",
            note="Claimed from unassigned queue",
        )
        await self.session.commit()
        agent = await self.auth_repo.get_user_by_id(agent_id)
        if agent:
            await self.send_assignment_emails(app, agent, None)

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

    async def get_agent_skills(self, agent_id: str) -> AgentSkillsResponse:
        agent = await self.auth_repo.get_user_by_id(agent_id)
        if agent is None or agent.role != "staff:agent":
            raise AgentNotFoundError()
        rows = await self.repo.get_agent_skills(agent_id)
        return AgentSkillsResponse(
            agent_id=agent_id,
            skills=[
                AgentSkillItem(
                    service_category=r.service_category,
                    proficiency_level=r.proficiency_level,
                    notes=r.notes,
                )
                for r in rows
            ],
        )

    async def set_agent_skills(
        self,
        *,
        agent_id: str,
        payload: SetAgentSkillsRequest,
    ) -> AgentSkillsResponse:
        agent = await self.auth_repo.get_user_by_id(agent_id)
        if agent is None or agent.role != "staff:agent":
            raise AgentNotFoundError()
        for skill in payload.skills:
            if skill.service_category not in SERVICE_CATEGORIES:
                raise InvalidServiceCategoryError()
        await self.repo.upsert_agent_skills(
            agent_id,
            [s.model_dump() for s in payload.skills],
        )
        await self.session.commit()
        return await self.get_agent_skills(agent_id)

    async def get_agent_metrics(self, agent_id: str) -> AgentMetricsResponse:
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (month_start - timedelta(days=1)).replace(day=1)
        completed_this = await self._count_completions(agent_id, month_start, now)
        completed_last = await self._count_completions(agent_id, last_month_start, month_start)
        completed_delta = self._pct_delta(completed_this, completed_last)
        avg_turn = await self._avg_turnaround_hours(agent_id, month_start, now)
        avg_last = await self._avg_turnaround_hours(agent_id, last_month_start, month_start)
        turn_delta = self._pct_delta(int(avg_turn), int(avg_last)) if avg_last else "+0%"
        on_time = await self._on_time_sla_percent(agent_id, month_start, now)
        weekly = await self._weekly_bars(agent_id)
        leaderboard = await self._leaderboard(agent_id, show_full_names=False)
        return AgentMetricsResponse(
            completedCount=completed_this,
            completedDelta=completed_delta,
            avgTurnaround=round(avg_turn, 1),
            avgTurnaroundDelta=turn_delta,
            onTimeSLAPercent=on_time,
            clientRating=4.5,
            ratingsCount=0,
            weeklyBars=weekly,
            leaderboard=leaderboard,
        )

    async def get_admin_leaderboard(self) -> LeaderboardResponse:
        return LeaderboardResponse(
            leaderboard=await self._leaderboard("", show_full_names=True),
        )

    async def _count_completions(self, agent_id: str, start: datetime, end: datetime) -> int:
        from sqlalchemy import func, select

        count = await self.session.scalar(
            select(func.count())
            .select_from(Application)
            .where(
                Application.assigned_agent_id == agent_id,
                Application.status == "completed",
                Application.completed_at >= start,
                Application.completed_at < end,
            )
        )
        return int(count or 0)

    async def _avg_turnaround_hours(self, agent_id: str, start: datetime, end: datetime) -> float:
        from sqlalchemy import select

        apps = list(
            await self.session.scalars(
                select(Application).where(
                    Application.assigned_agent_id == agent_id,
                    Application.status == "completed",
                    Application.completed_at.isnot(None),
                    Application.completed_at >= start,
                    Application.completed_at < end,
                )
            )
        )
        if not apps:
            return 0.0
        total = sum((a.completed_at - a.submitted_at).total_seconds() / 3600 for a in apps if a.completed_at)
        return total / len(apps)

    async def _on_time_sla_percent(self, agent_id: str, start: datetime, end: datetime) -> float:
        from sqlalchemy import select

        apps = list(
            await self.session.scalars(
                select(Application).where(
                    Application.assigned_agent_id == agent_id,
                    Application.status == "completed",
                    Application.completed_at.isnot(None),
                    Application.completed_at >= start,
                    Application.completed_at < end,
                )
            )
        )
        if not apps:
            return 100.0
        on_time = sum(
            1 for a in apps if a.sla_deadline and a.completed_at and a.completed_at <= a.sla_deadline
        )
        return round(on_time / len(apps) * 100, 1)

    async def _weekly_bars(self, agent_id: str) -> list[WeeklyBarResponse]:
        now = datetime.now(UTC)
        bars: list[WeeklyBarResponse] = []
        for i in range(9, -1, -1):
            week_start = (now - timedelta(days=now.weekday() + i * 7)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            week_end = week_start + timedelta(days=7)
            count = await self._count_completions(agent_id, week_start, week_end)
            label = week_start.strftime("%b %d")
            bars.append(
                WeeklyBarResponse(
                    week=label,
                    count=count,
                    isCurrent=i == 0,
                )
            )
        return bars

    async def _leaderboard(
        self,
        current_agent_id: str,
        *,
        show_full_names: bool,
    ) -> list[LeaderboardEntryResponse]:
        from sqlalchemy import select

        from app.modules.auth.models import User

        agents = list(
            await self.session.scalars(
                select(User).where(User.role == "staff:agent", User.is_active.is_(True))
            )
        )
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        entries: list[tuple[str, str, str, int]] = []
        for agent in agents:
            count = await self._count_completions(agent.user_id, month_start, now)
            parts = agent.name.split()
            initials = "".join(p[0].upper() for p in parts[:2]) or "?"
            entries.append((agent.user_id, agent.name, initials, count))
        entries.sort(key=lambda x: -x[3])
        result: list[LeaderboardEntryResponse] = []
        for user_id, name, initials, count in entries:
            is_me = user_id == current_agent_id
            display = name if show_full_names or is_me else initials
            if is_me and not show_full_names:
                display = "You"
            result.append(
                LeaderboardEntryResponse(
                    initials=initials,
                    name=display,
                    count=count,
                    isMe=is_me,
                )
            )
        return result

    def _pct_delta(self, current: int, previous: int) -> str:
        if previous == 0:
            return "+100%" if current > 0 else "+0%"
        change = ((current - previous) / previous) * 100
        sign = "+" if change >= 0 else ""
        return f"{sign}{int(change)}%"

    async def _validate_agent_available(self, agent_id: str) -> None:
        settings = await self.repo.get_or_create_settings(agent_id)
        if not settings.accepting_cases:
            raise AgentNotAvailableError()
        if settings.daily_case_cap is not None:
            count = await self.apps_repo.count_agent_assignments_today(agent_id)
            if count >= settings.daily_case_cap:
                raise DailyCapExceededError(cap=settings.daily_case_cap)

    async def send_assignment_emails(
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
