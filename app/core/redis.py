"""Async Redis client management."""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import Settings


class RedisManager:
    """Owns the shared Redis client."""

    def __init__(self) -> None:
        self.client: Redis | None = None

    def configure(self, settings: Settings) -> None:
        if self.client is not None:
            return
        self.client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)

    async def ping(self) -> bool:
        if self.client is None:
            raise RuntimeError("RedisManager is not configured")
        return bool(await self.client.ping())

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()


redis_manager = RedisManager()
