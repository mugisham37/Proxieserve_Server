"""Persistence helpers for applications."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.applications.models import (
    Application,
    ApplicationAssignmentHistory,
    ApplicationStatusHistory,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class ApplicationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_application(self, **kwargs: object) -> Application:
        app = Application(**kwargs)
        self.session.add(app)
        await self.session.flush()
        return app

    async def get_by_code(
        self,
        code: str,
        *,
        load_history: bool = False,
    ) -> Application | None:
        query = select(Application).where(Application.code == code)
        if load_history:
            query = query.options(
                selectinload(Application.status_history),
                selectinload(Application.assignment_history),
            )
        return cast(Application | None, await self.session.scalar(query))

    async def get_by_id(self, application_id: str) -> Application | None:
        return await self.session.get(Application, application_id)

    async def code_exists(self, code: str) -> bool:
        result = await self.session.scalar(
            select(Application.application_id).where(Application.code == code)
        )
        return result is not None

    async def list_by_client(self, client_id: str) -> list[Application]:
        query = (
            select(Application)
            .where(Application.client_id == client_id)
            .order_by(Application.submitted_at.desc())
        )
        return list(await self.session.scalars(query))

    async def list_by_agent(self, agent_id: str) -> list[Application]:
        query = (
            select(Application)
            .where(Application.assigned_agent_id == agent_id)
            .order_by(Application.submitted_at.desc())
        )
        return list(await self.session.scalars(query))

    async def list_unassigned(self) -> list[Application]:
        query = (
            select(Application)
            .where(Application.status == "received", Application.assigned_agent_id.is_(None))
            .order_by(Application.submitted_at.asc())
        )
        return list(await self.session.scalars(query))

    async def list_all(
        self,
        *,
        status: str | None = None,
        service_id: str | None = None,
        agent_id: str | None = None,
        tier: str | None = None,
        payment_status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Application], int]:
        query: Select[tuple[Application]] = select(Application)
        count_query = select(func.count()).select_from(Application)
        filters = []
        if status:
            filters.append(Application.status == status)
        if service_id:
            filters.append(Application.service_id == service_id)
        if agent_id:
            filters.append(Application.assigned_agent_id == agent_id)
        if tier:
            filters.append(Application.tier == tier)
        if payment_status:
            filters.append(Application.payment_status == payment_status)
        for f in filters:
            query = query.where(f)
            count_query = count_query.where(f)
        total = cast(int, await self.session.scalar(count_query))
        query = query.order_by(Application.submitted_at.desc()).offset(offset).limit(limit)
        return list(await self.session.scalars(query)), total

    async def get_for_update(self, code: str) -> Application | None:
        query = (
            select(Application)
            .where(Application.code == code)
            .with_for_update(skip_locked=True)
        )
        return cast(Application | None, await self.session.scalar(query))

    async def add_status_history(self, **kwargs: object) -> ApplicationStatusHistory:
        entry = ApplicationStatusHistory(**kwargs)
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def add_assignment_history(self, **kwargs: object) -> ApplicationAssignmentHistory:
        entry = ApplicationAssignmentHistory(**kwargs)
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def count_agent_assignments_today(self, agent_id: str) -> int:
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.scalar(
            select(func.count())
            .select_from(ApplicationAssignmentHistory)
            .where(
                ApplicationAssignmentHistory.new_agent_id == agent_id,
                ApplicationAssignmentHistory.created_at >= today_start,
            )
        )
        return int(result or 0)

    async def count_by_status(self) -> dict[str, int]:
        rows = await self.session.execute(
            select(Application.status, func.count())
            .group_by(Application.status)
        )
        return {status: count for status, count in rows.all()}

    async def count_by_service(self) -> list[tuple[str, str, int]]:
        rows = await self.session.execute(
            select(Application.service_name, Application.service_id, func.count())
            .group_by(Application.service_name, Application.service_id)
        )
        return [(name, sid, count) for name, sid, count in rows.all()]
