"""Dependency helpers for the auth module."""

from __future__ import annotations

from typing import Any

import jwt
from fastapi import Cookie, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import (
    get_app_settings,
    get_db_session,
    get_event_bus,
    get_job_queue,
    get_redis,
)
from app.core.events import EventBus
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.jobs import JobQueueManager
from app.core.security import decode_token
from app.modules.auth.constants import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from app.modules.auth.service import AuthService


async def get_auth_service(
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_app_settings),
    event_bus: EventBus = Depends(get_event_bus),
    job_queue: JobQueueManager = Depends(get_job_queue),
) -> AuthService:
    return AuthService(
        session=session,
        redis=redis,
        settings=settings,
        event_bus=event_bus,
        job_queue=job_queue,
    )


def get_access_token(access_token: str | None = Cookie(default=None, alias=ACCESS_COOKIE_NAME)) -> str | None:
    return access_token


def get_refresh_token(refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME)) -> str | None:
    return refresh_token


def require_access_payload(
    access_token: str | None = Depends(get_access_token),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    if access_token is None:
        raise UnauthorizedError()
    try:
        return decode_token(token=access_token, secret=settings.jwt_access_secret, settings=settings)
    except jwt.PyJWTError as exc:
        raise UnauthorizedError() from exc


def get_access_payload_optional(
    access_token: str | None = Depends(get_access_token),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any] | None:
    if access_token is None:
        return None
    try:
        return decode_token(token=access_token, secret=settings.jwt_access_secret, settings=settings)
    except jwt.PyJWTError:
        return None


def require_role(*allowed_roles: str) -> Any:
    """Dependency factory that enforces the caller has one of the allowed roles."""

    async def check(payload: dict[str, Any] = Depends(require_access_payload)) -> dict[str, Any]:
        if payload.get("role") not in allowed_roles:
            raise ForbiddenError()
        return payload

    return Depends(check)


def require_email_verified() -> Any:
    """Dependency that enforces the caller has verified their email."""

    async def check(payload: dict[str, Any] = Depends(require_access_payload)) -> dict[str, Any]:
        if not payload.get("isEmailVerified"):
            raise ForbiddenError(message="Email verification required.")
        return payload

    return Depends(check)


# Convenience aliases — use these in routers instead of inline require_role() calls.
REQUIRE_ADMIN = require_role("staff:admin")
REQUIRE_AGENT = require_role("staff:agent")
REQUIRE_AGENT_OR_ADMIN = require_role("staff:agent", "staff:admin")
REQUIRE_CLIENT = require_role("client")
