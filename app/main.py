"""Application factory for the ProxiServe backend."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.core.api import ApiResponse, success_response
from app.core.config import Settings, get_settings
from app.core.database import db_manager
from app.core.jobs import job_queue_manager
from app.core.logging import setup_logging
from app.core.middleware import configure_middleware, register_exception_handlers
from app.core.observability import configure_observability
from app.core.redis import redis_manager
from app.modules.applications.router import router as applications_router
from app.modules.auth.router import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.app_log_level)
    db_manager.configure(settings)
    redis_manager.configure(settings)
    await job_queue_manager.configure(settings)
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

    app.include_router(auth_router)
    app.include_router(applications_router)

    return app


app = create_app()
