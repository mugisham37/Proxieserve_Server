"""Persistence helpers for messages."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.messages.models import ApplicationMessage


def utc_now() -> datetime:
    return datetime.now(UTC)


class MessagesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_message(self, **kwargs: object) -> ApplicationMessage:
        message = ApplicationMessage(**kwargs)
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_for_client(self, application_id: str) -> list[ApplicationMessage]:
        query = (
            select(ApplicationMessage)
            .where(
                ApplicationMessage.application_id == application_id,
                ApplicationMessage.is_internal.is_(False),
            )
            .order_by(ApplicationMessage.created_at.asc())
        )
        return list(await self.session.scalars(query))

    async def list_for_staff(self, application_id: str) -> list[ApplicationMessage]:
        query = (
            select(ApplicationMessage)
            .where(ApplicationMessage.application_id == application_id)
            .order_by(ApplicationMessage.created_at.asc())
        )
        return list(await self.session.scalars(query))

    async def mark_read_by_client(self, application_id: str) -> int:
        result = await self.session.execute(
            update(ApplicationMessage)
            .where(
                ApplicationMessage.application_id == application_id,
                ApplicationMessage.is_internal.is_(False),
                ApplicationMessage.is_system.is_(False),
                ApplicationMessage.sender_role.in_(["staff:agent", "staff:admin"]),
                ApplicationMessage.is_read_by_client.is_(False),
            )
            .values(is_read_by_client=True)
        )
        await self.session.flush()
        return cast(int, result.rowcount)

    async def count_unread_for_client(self, application_id: str) -> int:
        from sqlalchemy import func

        result = await self.session.scalar(
            select(func.count())
            .select_from(ApplicationMessage)
            .where(
                ApplicationMessage.application_id == application_id,
                ApplicationMessage.is_internal.is_(False),
                ApplicationMessage.sender_role.in_(["staff:agent", "staff:admin"]),
                ApplicationMessage.is_read_by_client.is_(False),
            )
        )
        return int(result or 0)
