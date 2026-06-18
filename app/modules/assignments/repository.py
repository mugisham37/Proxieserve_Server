"""Persistence helpers for assignments."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.applications.constants import TERMINAL_STATUSES
from app.modules.applications.models import Application, ApplicationAssignmentHistory
from app.modules.assignments.models import AgentServiceSkill, AgentSettings
from app.modules.auth.models import RefreshToken, User


class AssignmentsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_agent_settings(self, user_id: str) -> AgentSettings | None:
        return await self.session.get(AgentSettings, user_id)

    async def get_or_create_settings(self, user_id: str) -> AgentSettings:
        settings = await self.get_agent_settings(user_id)
        if settings is not None:
            return settings
        settings = AgentSettings(user_id=user_id)
        self.session.add(settings)
        await self.session.flush()
        return settings

    async def update_settings(self, settings: AgentSettings, **kwargs: object) -> AgentSettings:
        for key, value in kwargs.items():
            setattr(settings, key, value)
        await self.session.flush()
        return settings

    async def get_agent_skills(self, agent_id: str) -> list[AgentServiceSkill]:
        query = select(AgentServiceSkill).where(AgentServiceSkill.agent_id == agent_id)
        return list(await self.session.scalars(query))

    async def upsert_agent_skills(
        self,
        agent_id: str,
        skills: list[dict[str, object]],
    ) -> list[AgentServiceSkill]:
        existing = await self.get_agent_skills(agent_id)
        for row in existing:
            await self.session.delete(row)
        await self.session.flush()
        from app.core.security import generate_id

        now = datetime.now(UTC)
        created: list[AgentServiceSkill] = []
        for skill in skills:
            row = AgentServiceSkill(
                id=generate_id("ask"),
                agent_id=agent_id,
                service_category=str(skill["service_category"]),
                proficiency_level=int(skill["proficiency_level"]),
                notes=skill.get("notes"),
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
            created.append(row)
        await self.session.flush()
        return created

    async def fetch_eligible_agents_data(self) -> list[dict[str, object]]:
        """Return eligible agents with settings and active case counts."""
        seven_days_ago = datetime.now(UTC) - timedelta(days=7)
        recent_session = (
            select(RefreshToken.user_id)
            .where(RefreshToken.created_at >= seven_days_ago)
            .distinct()
            .subquery()
        )
        active_counts = (
            select(
                Application.assigned_agent_id.label("agent_id"),
                func.count().label("active_count"),
            )
            .where(
                Application.assigned_agent_id.isnot(None),
                ~Application.status.in_(TERMINAL_STATUSES),
            )
            .group_by(Application.assigned_agent_id)
            .subquery()
        )
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_counts = (
            select(
                ApplicationAssignmentHistory.new_agent_id.label("agent_id"),
                func.count().label("daily_count"),
            )
            .where(ApplicationAssignmentHistory.created_at >= today_start)
            .group_by(ApplicationAssignmentHistory.new_agent_id)
            .subquery()
        )
        last_assigned = (
            select(
                ApplicationAssignmentHistory.new_agent_id.label("agent_id"),
                func.max(ApplicationAssignmentHistory.created_at).label("last_assigned_at"),
            )
            .group_by(ApplicationAssignmentHistory.new_agent_id)
            .subquery()
        )
        query = (
            select(
                User.user_id,
                User.name,
                AgentSettings.daily_case_cap,
                func.coalesce(active_counts.c.active_count, 0),
                func.coalesce(daily_counts.c.daily_count, 0),
                last_assigned.c.last_assigned_at,
            )
            .join(AgentSettings, AgentSettings.user_id == User.user_id)
            .outerjoin(active_counts, active_counts.c.agent_id == User.user_id)
            .outerjoin(daily_counts, daily_counts.c.agent_id == User.user_id)
            .outerjoin(last_assigned, last_assigned.c.agent_id == User.user_id)
            .where(
                User.role == "staff:agent",
                User.is_active.is_(True),
                AgentSettings.accepting_cases.is_(True),
                User.user_id.in_(select(recent_session.c.user_id)),
            )
        )
        rows = await self.session.execute(query)
        result = []
        for user_id, name, cap, active, daily, last_at in rows.all():
            if cap is not None and daily >= cap:
                continue
            result.append(
                {
                    "user_id": user_id,
                    "name": name,
                    "daily_case_cap": cap,
                    "active_count": int(active),
                    "last_assigned_at": last_at,
                }
            )
        return result

    async def fetch_skills_for_agents(self, agent_ids: list[str]) -> dict[str, list[AgentServiceSkill]]:
        if not agent_ids:
            return {}
        rows = list(
            await self.session.scalars(
                select(AgentServiceSkill).where(AgentServiceSkill.agent_id.in_(agent_ids))
            )
        )
        out: dict[str, list[AgentServiceSkill]] = {aid: [] for aid in agent_ids}
        for row in rows:
            out.setdefault(row.agent_id, []).append(row)
        return out

    async def fetch_sla_compliance_rates(self, agent_ids: list[str]) -> dict[str, float]:
        if not agent_ids:
            return {}
        thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
        from sqlalchemy import case

        rows = await self.session.execute(
            select(
                Application.assigned_agent_id,
                func.count(),
                func.sum(
                    case(
                        (Application.completed_at <= Application.sla_deadline, 1),
                        else_=0,
                    )
                ),
            )
            .where(
                Application.assigned_agent_id.in_(agent_ids),
                Application.status.in_(("completed", "rejected")),
                Application.completed_at.isnot(None),
                Application.completed_at >= thirty_days_ago,
            )
            .group_by(Application.assigned_agent_id)
        )
        rates: dict[str, float] = {}
        for agent_id, total, on_time in rows.all():
            if total:
                rates[str(agent_id)] = float(on_time or 0) / float(total) * 100.0
        return rates
