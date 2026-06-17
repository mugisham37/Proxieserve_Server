"""Alembic environment — async SQLAlchemy setup."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ── Import every model module so SQLAlchemy registers their tables ────────────
import app.modules.auth.models  # noqa: F401, E402
import app.modules.services.models  # noqa: F401, E402
import app.modules.applications.models  # noqa: F401, E402
import app.modules.messages.models  # noqa: F401, E402
import app.modules.documents.models  # noqa: F401, E402
import app.modules.assignments.models  # noqa: F401, E402

# ── Pull settings from .env so alembic.ini never needs a hardcoded URL ───────
from app.core.config import get_settings  # noqa: E402

# ── Import Base so its metadata is populated ─────────────────────────────────
from app.core.database import Base  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Alembic Config object — gives access to values in alembic.ini
# ─────────────────────────────────────────────────────────────────────────────
config = context.config

# Override sqlalchemy.url with the value derived from .env
config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Wire up Python logging from the ini file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata object that autogenerate will diff against the live DB
target_metadata = Base.metadata


# ─────────────────────────────────────────────────────────────────────────────
# Offline mode — emit raw SQL without a live DB connection
# ─────────────────────────────────────────────────────────────────────────────
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ─────────────────────────────────────────────────────────────────────────────
# Online mode — async engine + connection
# ─────────────────────────────────────────────────────────────────────────────
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    settings = get_settings()
    connect_args: dict[str, object] = {"ssl": "require"} if settings.postgres_ssl else {}
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ─────────────────────────────────────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
