"""Broadcast business logic."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jobs import JobQueueManager
from app.core.security import generate_id
from app.modules.auth.models import User
from app.modules.broadcasts.repository import BroadcastsRepository
from app.modules.broadcasts.schemas import (
    BroadcastListResponse,
    BroadcastRecordResponse,
    CreateBroadcastRequest,
)


class BroadcastsService:
    def __init__(
        self,
        session: AsyncSession,
        job_queue: JobQueueManager | None = None,
    ) -> None:
        self.session = session
        self.job_queue = job_queue
        self.repo = BroadcastsRepository(session)

    async def _estimate_reach(self, audience_filter: dict[str, object]) -> int:
        if audience_filter.get("all"):
            count = await self.session.scalar(
                select(func.count()).select_from(User).where(User.role == "client")
            )
            return int(count or 0)
        from app.modules.applications.models import Application

        if audience_filter.get("service_slug"):
            count = await self.session.scalar(
                select(func.count())
                .select_from(Application)
                .where(Application.service_slug == str(audience_filter["service_slug"]))
            )
            return int(count or 0)
        return 0

    async def list_broadcasts(self) -> BroadcastListResponse:
        rows = await self.repo.list_all()
        return BroadcastListResponse(
            broadcasts=[
                BroadcastRecordResponse(
                    id=row.id,
                    audience=row.audience_description,
                    channels=row.channels,
                    message=row.message,
                    sentAt=row.sent_at.isoformat() if row.sent_at else "",
                    reach=row.actual_reach or 0,
                )
                for row in rows
            ]
        )

    async def create_broadcast(
        self,
        *,
        admin_id: str,
        payload: CreateBroadcastRequest,
    ) -> BroadcastRecordResponse:
        estimated = await self._estimate_reach(payload.audience_filter)
        now = datetime.now(UTC)
        row = await self.repo.create(
            id=generate_id("brc"),
            created_by=admin_id,
            audience_description=payload.audience_description,
            audience_filter=payload.audience_filter,
            channels=payload.channels,
            message=payload.message,
            scheduled_at=payload.scheduled_at,
            estimated_reach=estimated,
            broadcast_status="scheduled" if payload.scheduled_at else "draft",
            created_at=now,
        )
        await self.session.commit()
        if self.job_queue:
            if payload.scheduled_at:
                defer = max(0, int((payload.scheduled_at - now).total_seconds()))
                await self.job_queue.enqueue(
                    "broadcast_send_job",
                    broadcast_id=row.id,
                    _defer_by=defer,
                )
            else:
                await self.job_queue.enqueue("broadcast_send_job", broadcast_id=row.id)
        return BroadcastRecordResponse(
            id=row.id,
            audience=row.audience_description,
            channels=row.channels,
            message=row.message,
            sentAt="",
            reach=0,
        )
