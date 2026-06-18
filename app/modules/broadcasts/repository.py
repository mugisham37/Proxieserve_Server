"""Broadcast persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.broadcasts.models import Broadcast


class BroadcastsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: object) -> Broadcast:
        row = Broadcast(**kwargs)
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_all(self) -> list[Broadcast]:
        query = select(Broadcast).order_by(Broadcast.created_at.desc())
        return list(await self.session.scalars(query))

    async def get_by_id(self, broadcast_id: str) -> Broadcast | None:
        return await self.session.get(Broadcast, broadcast_id)
