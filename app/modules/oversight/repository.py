"""Oversight persistence."""

from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.oversight.models import ApplicationEscalation


class OversightRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_escalation(self, **kwargs: object) -> ApplicationEscalation:
        row = ApplicationEscalation(**kwargs)
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_active_escalation(self, application_id: str) -> ApplicationEscalation | None:
        query = (
            select(ApplicationEscalation)
            .where(
                ApplicationEscalation.application_id == application_id,
                ApplicationEscalation.oversight_status == "escalated",
            )
            .order_by(ApplicationEscalation.created_at.desc())
            .limit(1)
        )
        return cast(ApplicationEscalation | None, await self.session.scalar(query))
