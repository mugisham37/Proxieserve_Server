"""Application factory for the ProxiServe backend."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy import select, text

from app.core.api import ApiResponse, success_response
from app.core.config import Settings, get_settings
from app.core.database import db_manager
from app.core.jobs import job_queue_manager
from app.core.logging import setup_logging
from app.core.middleware import configure_middleware, register_exception_handlers
from app.core.observability import configure_observability
from app.core.redis import redis_manager
from app.core.security import generate_id
from app.modules.auth.models import StaffProfile, User
from app.modules.auth.router import router as auth_router
from app.seed import seed_dev_services, seed_platform_settings

_logger = logging.getLogger(__name__)

_ADMIN_EMAIL = "mugisham505@gmail.com"
# Argon2id hash of the admin password — safe to store, cannot be reversed.
_ADMIN_PW_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4"
    "$mIYZRUShQKZaxhelZngjXA"
    "$P1bzou2NrT+UuMAiOfKeS7I36GO8sgtvqMshcXHJ3jw"
)


async def _seed_admin() -> None:
    """Ensure the permanent admin account exists in the database (idempotent)."""
    if db_manager.session_factory is None:
        raise RuntimeError("DatabaseManager is not configured")
    async with db_manager.session_factory() as session:
        existing = await session.scalar(select(User).where(User.role == "staff:admin").limit(1))
        if existing is not None:
            _logger.info("Admin account already exists — skipping seed.")
            return

        user_id = generate_id("usr")
        now = datetime.now(UTC)
        user = User(
            user_id=user_id,
            name="Admin",
            email=_ADMIN_EMAIL,
            phone_e164=None,
            password_hash=_ADMIN_PW_HASH,
            role="staff:admin",
            is_active=True,
            is_email_verified=True,
            language="en",
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        await session.flush()

        profile = StaffProfile(
            user_id=user_id,
            totp_secret_encrypted=None,
            twofa_enabled=True,
            sms_phone_e164=None,
            created_at=now,
        )
        session.add(profile)
        await session.commit()
        _logger.info("Admin account created for %s.", _ADMIN_EMAIL)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.app_log_level)
    db_manager.configure(settings)
    redis_manager.configure(settings)
    await job_queue_manager.configure(settings)
    import os

    os.makedirs(settings.upload_dir, exist_ok=True)
    await _seed_admin()
    await seed_dev_services()
    await seed_platform_settings()
    yield
    await job_queue_manager.close()
    await redis_manager.close()
    await db_manager.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(
        title=app_settings.app_name,
        debug=app_settings.app_debug,
        version="0.1.0",
        lifespan=lifespan,
    )
    configure_middleware(app, app_settings)
    register_exception_handlers(app)
    configure_observability(app, app_settings)

    @app.get("/", response_model=ApiResponse[dict[str, str]])
    async def root() -> ApiResponse[dict[str, str]]:
        return success_response(
            message="ProxiServe server is running.",
            data={"service": app_settings.app_name, "environment": app_settings.app_env},
        )

    @app.get(app_settings.health_path, response_model=ApiResponse[dict[str, str]])
    async def health() -> ApiResponse[dict[str, str]]:
        return success_response(message="Service is healthy.", data={"status": "ok"})

    @app.get(app_settings.ready_path, response_model=ApiResponse[dict[str, str]])
    async def ready() -> ApiResponse[dict[str, str]]:
        if redis_manager.client is None:
            raise RuntimeError("RedisManager is not configured")
        await redis_manager.ping()
        if db_manager.engine is None:
            raise RuntimeError("DatabaseManager is not configured")
        async with db_manager.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return success_response(message="Dependencies are ready.", data={"status": "ready"})

    from app.modules.admin.router import router as admin_router
    from app.modules.applications.router import (
        admin_router as applications_admin_router,
    )
    from app.modules.applications.router import (
        agent_router as applications_agent_router,
    )
    from app.modules.applications.router import (
        analytics_router,
        tracker_router,
    )
    from app.modules.applications.router import (
        client_router as applications_client_router,
    )
    from app.modules.applications.router import (
        legacy_router as applications_legacy_router,
    )
    from app.modules.assignments.router import admin_router as assignments_admin_router
    from app.modules.assignments.router import agent_router as assignments_agent_router
    from app.modules.audit.router import router as audit_router
    from app.modules.broadcasts.router import router as broadcasts_router
    from app.modules.documents.router import (
        agent_router as documents_agent_router,
    )
    from app.modules.documents.router import (
        client_router as documents_client_router,
    )
    from app.modules.documents.router import (
        download_router as documents_download_router,
    )
    from app.modules.messages.router import (
        admin_router as messages_admin_router,
    )
    from app.modules.messages.router import (
        agent_router as messages_agent_router,
    )
    from app.modules.messages.router import (
        client_router as messages_client_router,
    )
    from app.modules.oversight.router import router as oversight_router
    from app.modules.payments.router import router as payments_router
    from app.modules.platform.router import router as platform_router
    from app.modules.services.router import admin_router as services_admin_router
    from app.modules.services.router import public_router as services_public_router

    app.include_router(auth_router)
    app.include_router(platform_router)
    app.include_router(services_public_router)
    app.include_router(services_admin_router)
    app.include_router(applications_client_router)
    app.include_router(applications_legacy_router)
    app.include_router(documents_client_router)
    app.include_router(messages_client_router)
    app.include_router(tracker_router)
    app.include_router(payments_router)
    app.include_router(applications_agent_router)
    app.include_router(documents_agent_router)
    app.include_router(messages_agent_router)
    app.include_router(assignments_agent_router)
    app.include_router(applications_admin_router)
    app.include_router(messages_admin_router)
    app.include_router(analytics_router)
    app.include_router(oversight_router)
    app.include_router(audit_router)
    app.include_router(broadcasts_router)
    app.include_router(assignments_admin_router)
    app.include_router(documents_download_router)
    app.include_router(admin_router)

    return app


app = create_app()
