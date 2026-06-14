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

_SENSITIVE_FIELDS = frozenset(
    {"password", "new_password", "confirm_password", "token", "otp", "code", "secret", "refresh_token"}
)
_SKIP_HEADER_NAMES = frozenset({"authorization", "cookie", "x-forwarded-for", "host"})


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


def _filter_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _SKIP_HEADER_NAMES}


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

        # Read and cache body before handing off to the route handler.
        # Starlette caches it in request._body so downstream reads work normally.
        body_bytes = await request.body()

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
            "headers": _filter_headers(dict(request.headers)),
        }

        query = str(request.url.query)
        if query:
            log_kwargs["query"] = query

        if request.method in {"POST", "PUT", "PATCH"} and body_bytes:
            sanitized = _sanitize_body(body_bytes)
            if sanitized is not None:
                log_kwargs["body"] = sanitized

        if response.status_code >= 400:
            logger.warning("request_complete", **log_kwargs)
        else:
            logger.info("request_complete", **log_kwargs)

        structlog.contextvars.clear_contextvars()
        return response
