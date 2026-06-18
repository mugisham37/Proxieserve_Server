"""Audit log persistence."""

from __future__ import annotations

from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_entry(self, **kwargs: object) -> AuditLog:
        entry = AuditLog(**kwargs)
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_entries(
        self,
        *,
        kind_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int, bool]:
        query = select(AuditLog).order_by(AuditLog.created_at.desc())
        count_query = select(func.count()).select_from(AuditLog)
        if kind_filter and kind_filter != "all":
            query = query.where(AuditLog.kind == kind_filter)
            count_query = count_query.where(AuditLog.kind == kind_filter)
        total = cast(int, await self.session.scalar(count_query))
        rows = list(await self.session.scalars(query.offset(offset).limit(limit + 1)))
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]
        return rows, total, has_more
