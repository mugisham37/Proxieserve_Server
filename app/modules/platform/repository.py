"""Platform settings persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.platform.models import PlatformSettings


class PlatformRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self) -> PlatformSettings:
        row = await self.session.get(PlatformSettings, "global")
        if row is not None:
            return row
        now = datetime.now(UTC)
        row = PlatformSettings(id="global", updated_at=now)
        self.session.add(row)
        await self.session.flush()
        return row
