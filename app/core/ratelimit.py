"""Redis-backed rate limiting helpers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from hashlib import sha256

from fastapi import Depends, Request
from redis.asyncio import Redis

from app.core.dependencies import get_redis
from app.core.exceptions import RateLimitedError


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def enforce(self, *, key: str, limit: int, window_seconds: int) -> None:
        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, window_seconds)
        if current > limit:
            raise RateLimitedError(retry_after_seconds=window_seconds)


def rate_limit(name: str, limit: int, window_seconds: int) -> Callable[[Request, Redis], Awaitable[None]]:
    async def dependency(request: Request, redis: Redis = Depends(get_redis)) -> None:
        client_host = request.client.host if request.client else "unknown"
        raw = f"{name}:{client_host}:{request.url.path}"
        key = f"ratelimit:{sha256(raw.encode('utf-8')).hexdigest()}"
        limiter = RedisRateLimiter(redis)
        await limiter.enforce(key=key, limit=limit, window_seconds=window_seconds)

    return dependency
