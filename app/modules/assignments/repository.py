"""Persistence helpers for assignments."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assignments.models import AgentSettings


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
