"""Broadcast background jobs."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.core.database import db_manager
from app.core.jobs import job_queue_manager
from app.core.logging import get_logger
from app.modules.auth.models import User
from app.modules.broadcasts.repository import BroadcastsRepository

logger = get_logger("broadcast_jobs")


async def _resolve_audience_user_ids(session, audience_filter: dict[str, object]) -> list[str]:
    if audience_filter.get("all"):
        rows = await session.scalars(select(User.user_id).where(User.role == "client"))
        return list(rows.all())
    query = select(User.user_id).where(User.role == "client")
    if service_slug := audience_filter.get("service_slug"):
        from app.modules.applications.models import Application

        subq = select(Application.client_id).where(Application.service_slug == str(service_slug))
        query = query.where(User.user_id.in_(subq))
    rows = await session.scalars(query)
    return list(rows.all())


async def broadcast_send_job(ctx: dict[str, object], *, broadcast_id: str) -> None:
    if db_manager.session_factory is None:
        raise RuntimeError("DatabaseManager is not configured")
    async with db_manager.session_factory() as session:
        repo = BroadcastsRepository(session)
        broadcast = await repo.get_by_id(broadcast_id)
        if broadcast is None:
            return
        broadcast.broadcast_status = "sending"
        await session.commit()
        user_ids = await _resolve_audience_user_ids(session, broadcast.audience_filter)
        sent = 0
        for user_id in user_ids:
            user = await session.get(User, user_id)
            if user is None or not user.email:
                continue
            if "email" not in broadcast.channels:
                continue
            try:
                if job_queue_manager.redis:
                    await job_queue_manager.enqueue(
                        "send_email_job",
                        to=user.email,
                        subject="Message from ProxiServe",
                        body=broadcast.message,
                    )
                    sent += 1
            except Exception:
                logger.exception("broadcast_send_failed", user_id=user_id)
        broadcast.actual_reach = sent
        broadcast.sent_at = datetime.now(UTC)
        broadcast.broadcast_status = "sent" if sent > 0 else "failed"
        await session.commit()
