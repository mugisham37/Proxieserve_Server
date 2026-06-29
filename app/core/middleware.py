"""Middleware and exception registration."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.core.api import error_response
from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.database import db_manager
from app.core.redis import redis_manager

_SENSITIVE_FIELDS = frozenset(
    {"password", "new_password", "confirm_password", "token", "otp", "code", "secret", "refresh_token"}
)

_MAINTENANCE_EXEMPT_PATHS = frozenset({"/health", "/ready", "/metrics", "/"})
_MAINTENANCE_REDIS_KEY = "platform:maintenance_mode"
_MAINTENANCE_REDIS_TTL_SECONDS = 60
_MAINTENANCE_MEMORY_TTL_SECONDS = 60.0

_maintenance_memory_cache: tuple[bool, float] | None = None


def invalidate_maintenance_mode_cache() -> None:
    """Clear in-process maintenance cache after admin settings change."""
    global _maintenance_memory_cache
    _maintenance_memory_cache = None


async def invalidate_maintenance_mode_cache_async() -> None:
    """Clear in-process and Redis maintenance cache after admin settings change."""
    invalidate_maintenance_mode_cache()
    if redis_manager.client is not None:
        await redis_manager.client.delete(_MAINTENANCE_REDIS_KEY)


def _sanitize_body(raw: bytes) -> dict | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return {k: "***" if k in _SENSITIVE_FIELDS else v for k, v in parsed.items()}


def _should_check_maintenance(request: Request) -> bool:
    if request.method == "OPTIONS":
        return False
    if request.url.path.startswith("/api/admin"):
        return False
    return request.url.path not in _MAINTENANCE_EXEMPT_PATHS


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(
                message=exc.message,
                error_type=exc.error_type,
                data=exc.data or None,
            ).model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger = structlog.get_logger("exceptions")
        logger.exception("unhandled_exception", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content=error_response(
                message="An unexpected server error occurred.",
                error_type="internal-error",
            ).model_dump(mode="json"),
        )


def configure_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Request-Id"],
    )

    logger = structlog.get_logger("http")

    @app.middleware("http")
    async def request_context_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        start = time.perf_counter()
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)

        body_bytes = b""
        if request.method in {"POST", "PUT", "PATCH"}:
            # Cache body before the route handler so error logging can sanitize it.
            body_bytes = await request.body()

        if _should_check_maintenance(request):
            maintenance = await _get_maintenance_mode()
            if maintenance:
                return JSONResponse(
                    status_code=503,
                    content=error_response(
                        message="The platform is temporarily unavailable for maintenance.",
                        error_type="maintenance-mode",
                    ).model_dump(mode="json"),
                )

        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = request_id
        response.headers["x-process-time-ms"] = f"{duration_ms:.2f}"
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["referrer-policy"] = "strict-origin-when-cross-origin"
        response.headers["x-frame-options"] = "DENY"

        log_kwargs: dict = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        }

        query = str(request.url.query)
        if query:
            log_kwargs["query"] = query

        if response.status_code >= 400 and request.method in {"POST", "PUT", "PATCH"} and body_bytes:
            sanitized = _sanitize_body(body_bytes)
            if sanitized is not None:
                log_kwargs["body"] = sanitized

        if response.status_code >= 400:
            logger.warning("request_complete", **log_kwargs)
        else:
            logger.info("request_complete", **log_kwargs)

        structlog.contextvars.clear_contextvars()
        return response


async def _get_maintenance_mode() -> bool:
    cache_key = "platform:maintenance_mode"
    if redis_manager.client is not None:
        cached = await redis_manager.client.get(cache_key)
        if cached is not None:
            return cached == b"1"
    if db_manager.session_factory is None:
        return False
    from app.modules.platform.repository import PlatformRepository

    async with db_manager.session_factory() as session:
        repo = PlatformRepository(session)
        settings = await repo.get_or_create()
        value = settings.maintenance_mode
        await session.commit()
    if redis_manager.client is not None:
        await redis_manager.client.setex(cache_key, 5, "1" if value else "0")
    return value
