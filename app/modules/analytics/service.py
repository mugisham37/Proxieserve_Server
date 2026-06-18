"""Admin analytics aggregation service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.schemas import (
    AdminAgent,
    AdminMetric,
    AlertItem,
    AnalyticsResponse,
    PaymentMixBar,
    ServiceMixBar,
    StatusBreakdown,
    WeeklyBar,
)
from app.modules.applications.constants import TERMINAL_STATUSES, compute_sla_state
from app.modules.applications.models import Application
from app.modules.assignments.models import AgentServiceSkill, AgentSettings
from app.modules.auth.models import RefreshToken, StaffProfile, User
from app.modules.documents.models import ApplicationDocument
from app.modules.payments.models import Payment
from app.modules.services.models import Service

STATUS_COLORS = {
    "received": "#94A3B8",
    "under_review": "#3B82F6",
    "in_progress": "#8B5CF6",
    "awaiting_client": "#F59E0B",
    "submitted_to_authority": "#06B6D4",
    "awaiting_response": "#64748B",
    "completed": "#22C55E",
    "rejected": "#EF4444",
    "cancelled": "#9CA3AF",
}

PAYMENT_COLORS = {
    "MTN Mobile Money": "#FFCC00",
    "Airtel Money": "#E40000",
    "Card": "#2563EB",
    "Agent Cash": "#16A34A",
    "Pending": "#9CA3AF",
}


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_analytics(self) -> AnalyticsResponse:
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        metrics = await self._build_metrics(now, month_start, week_start)
        weekly_bars = await self._weekly_bars(now)
        service_mix = await self._service_mix(now)
        payment_mix = await self._payment_mix()
        status_breakdown = await self._status_breakdown()
        alerts = await self._alerts(now)
        agents = await self._agents(now)
        return AnalyticsResponse(
            metrics=metrics,
            weeklyBars=weekly_bars,
            serviceMix=service_mix,
            paymentMix=payment_mix,
            statusBreakdown=status_breakdown,
            alerts=alerts,
            agents=agents,
        )

    async def _build_metrics(
        self,
        now: datetime,
        month_start: datetime,
        week_start: datetime,
    ) -> list[AdminMetric]:
        total_month = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Application)
                .where(Application.submitted_at >= month_start)
            )
            or 0
        )
        completed_week = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Application)
                .where(
                    Application.completed_at.isnot(None),
                    Application.completed_at >= week_start,
                )
            )
            or 0
        )
        completed_apps = list(
            await self.session.scalars(
                select(Application).where(
                    Application.status == "completed",
                    Application.completed_at.isnot(None),
                    Application.completed_at >= month_start,
                )
            )
        )
        if completed_apps:
            avg_hours = sum(
                (a.completed_at - a.submitted_at).total_seconds() / 3600
                for a in completed_apps
                if a.completed_at
            ) / len(completed_apps)
            avg_label = f"{avg_hours:.1f}h" if avg_hours < 48 else f"{avg_hours / 24:.1f}d"
        else:
            avg_label = "—"
        sla_total = len(completed_apps)
        sla_on_time = sum(
            1
            for a in completed_apps
            if a.sla_deadline and a.completed_at and a.completed_at <= a.sla_deadline
        )
        sla_pct = (sla_on_time / sla_total * 100) if sla_total else 100.0
        revenue = int(
            await self.session.scalar(
                select(func.coalesce(func.sum(Payment.amount_rwf), 0)).where(
                    Payment.status == "paid",
                    Payment.paid_at >= month_start,
                )
            )
            or 0
        )
        active_agents = int(
            await self.session.scalar(
                select(func.count())
                .select_from(User)
                .join(AgentSettings, AgentSettings.user_id == User.user_id)
                .where(
                    User.role == "staff:agent",
                    User.is_active.is_(True),
                    AgentSettings.accepting_cases.is_(True),
                )
            )
            or 0
        )
        return [
            AdminMetric(id="apps-month", label="Applications this month", value=total_month),
            AdminMetric(id="completed-week", label="Completed this week", value=completed_week),
            AdminMetric(id="avg-turnaround", label="Avg turnaround", value=avg_label),
            AdminMetric(id="sla-compliance", label="SLA compliance", value=f"{sla_pct:.0f}%"),
            AdminMetric(id="revenue", label="Revenue (RWF)", value=revenue),
            AdminMetric(id="active-agents", label="Active agents", value=active_agents),
        ]

    async def _weekly_bars(self, now: datetime) -> list[WeeklyBar]:
        bars: list[WeeklyBar] = []
        for i in range(9, -1, -1):
            start = (now - timedelta(days=now.weekday() + i * 7)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end = start + timedelta(days=7)
            count = int(
                await self.session.scalar(
                    select(func.count())
                    .select_from(Application)
                    .where(Application.submitted_at >= start, Application.submitted_at < end)
                )
                or 0
            )
            bars.append(WeeklyBar(week=start.strftime("%b %d"), count=count))
        return bars

    async def _service_mix(self, now: datetime) -> list[ServiceMixBar]:
        thirty_days = now - timedelta(days=30)
        rows = await self.session.execute(
            select(Application.service_name, Service.color, func.count())
            .join(Service, Service.service_id == Application.service_id)
            .where(Application.submitted_at >= thirty_days)
            .group_by(Application.service_name, Service.color)
        )
        data = rows.all()
        total = sum(r[2] for r in data) or 1
        return [
            ServiceMixBar(
                service=name,
                pct=round(count / total * 100, 1),
                color=color or "#3498DB",
            )
            for name, color, count in data
        ]

    async def _payment_mix(self) -> list[PaymentMixBar]:
        apps = list(await self.session.scalars(select(Application)))
        counts: dict[str, int] = {"Pending": 0}
        for app in apps:
            pay = await self.session.scalar(
                select(Payment.method)
                .where(Payment.application_id == app.application_id, Payment.status == "paid")
                .limit(1)
            )
            if pay == "mtn-momo":
                key = "MTN Mobile Money"
            elif pay == "airtel-money":
                key = "Airtel Money"
            elif pay == "card":
                key = "Card"
            elif pay == "agent":
                key = "Agent Cash"
            else:
                key = "Pending"
            counts[key] = counts.get(key, 0) + 1
        total = sum(counts.values()) or 1
        return [
            PaymentMixBar(
                method=method,
                pct=round(count / total * 100, 1),
                color=PAYMENT_COLORS.get(method, "#9CA3AF"),
            )
            for method, count in counts.items()
        ]

    async def _status_breakdown(self) -> list[StatusBreakdown]:
        rows = await self.session.execute(
            select(Application.status, func.count()).group_by(Application.status)
        )
        data = rows.all()
        total = sum(r[1] for r in data) or 1
        labels = {
            "received": "Received",
            "under_review": "Under review",
            "in_progress": "In progress",
            "awaiting_client": "Awaiting client",
            "submitted_to_authority": "At authority",
            "awaiting_response": "Awaiting response",
            "completed": "Completed",
            "rejected": "Rejected",
            "cancelled": "Cancelled",
        }
        return [
            StatusBreakdown(
                label=labels.get(status, status),
                count=count,
                pct=round(count / total * 100, 1),
                color=STATUS_COLORS.get(status, "#94A3B8"),
            )
            for status, count in data
        ]

    async def _alerts(self, now: datetime) -> list[AlertItem]:
        alerts: list[AlertItem] = []
        apps = list(
            await self.session.scalars(
                select(Application).where(~Application.status.in_(TERMINAL_STATUSES))
            )
        )
        for app in apps:
            if compute_sla_state(app, now=now) == "over":
                alerts.append(
                    AlertItem(
                        id=f"sla-{app.code}",
                        message=f"SLA breached: {app.code} ({app.service_name})",
                        severity="danger",
                        cta="View",
                        ctaHref=f"/admin/oversight",
                    )
                )
        fail_docs = list(
            await self.session.scalars(
                select(ApplicationDocument).where(ApplicationDocument.qc_status == "fail")
            )
        )
        for doc in fail_docs:
            app = await self.session.get(Application, doc.application_id)
            if app and app.status not in TERMINAL_STATUSES:
                alerts.append(
                    AlertItem(
                        id=f"doc-{doc.document_id}",
                        message=f"Document QC failed for {app.code}",
                        severity="warn",
                    )
                )
        unassigned = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Application)
                .where(Application.status == "received", Application.assigned_agent_id.is_(None))
            )
            or 0
        )
        if unassigned > 5:
            alerts.append(
                AlertItem(
                    id="unassigned-queue",
                    message=f"{unassigned} applications awaiting assignment",
                    severity="warn",
                )
            )
        return alerts

    async def _agents(self, now: datetime) -> list[AdminAgent]:
        day_ago = now - timedelta(hours=24)
        agents = list(
            await self.session.scalars(
                select(User)
                .join(AgentSettings, AgentSettings.user_id == User.user_id)
                .where(User.role == "staff:agent", User.is_active.is_(True))
            )
        )
        result: list[AdminAgent] = []
        for agent in agents:
            settings = await self.session.get(AgentSettings, agent.user_id)
            profile = await self.session.get(StaffProfile, agent.user_id)
            skills_rows = list(
                await self.session.scalars(
                    select(AgentServiceSkill.service_category).where(
                        AgentServiceSkill.agent_id == agent.user_id
                    )
                )
            )
            active = int(
                await self.session.scalar(
                    select(func.count())
                    .select_from(Application)
                    .where(
                        Application.assigned_agent_id == agent.user_id,
                        ~Application.status.in_(TERMINAL_STATUSES),
                    )
                )
                or 0
            )
            completed_total = int(
                await self.session.scalar(
                    select(func.count())
                    .select_from(Application)
                    .where(
                        Application.assigned_agent_id == agent.user_id,
                        Application.status == "completed",
                    )
                )
                or 0
            )
            recent = await self.session.scalar(
                select(func.max(RefreshToken.created_at)).where(
                    RefreshToken.user_id == agent.user_id
                )
            )
            if settings and settings.accepting_cases:
                if recent and recent >= day_ago:
                    status = "active"
                else:
                    status = "away"
            else:
                status = "offline"
            parts = agent.name.split()
            initials = "".join(p[0].upper() for p in parts[:2]) or "?"
            capacity = settings.daily_case_cap if settings and settings.daily_case_cap else 20
            result.append(
                AdminAgent(
                    id=agent.user_id,
                    fullName=agent.name,
                    initials=initials,
                    email=agent.email or "",
                    skills=list(skills_rows),
                    load=active,
                    capacity=capacity,
                    twoFa=bool(profile.twofa_enabled) if profile else False,
                    role="AGENT",
                    status=status,
                    activeCases=active,
                    completedTotal=completed_total,
                    avgTurnaround="—",
                    slaPercent=100.0,
                    rating=4.5,
                )
            )
        return result
