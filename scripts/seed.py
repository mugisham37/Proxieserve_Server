"""One-time / manual database seeding for local development."""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.database import db_manager
from app.seed import seed_dev_services, seed_platform_settings


async def main() -> None:
    settings = get_settings()
    db_manager.configure(settings)
    await seed_dev_services()
    await seed_platform_settings()
    await db_manager.dispose()


if __name__ == "__main__":
    asyncio.run(main())
