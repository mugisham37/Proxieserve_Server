"""Background job queue management."""

from __future__ import annotations

from typing import Any, cast

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import Settings


class JobQueueManager:
    def __init__(self) -> None:
        self.redis: ArqRedis | None = None
        self.redis_settings: RedisSettings | None = None

    async def configure(self, settings: Settings) -> None:
        if self.redis is not None:
            return
        self.redis_settings = RedisSettings.from_dsn(settings.redis_url)
        self.redis = await create_pool(self.redis_settings)

    async def enqueue(self, job_name: str, **kwargs: object) -> None:
        if self.redis is None:
            raise RuntimeError("JobQueueManager is not configured")
        await cast(Any, self.redis).enqueue_job(job_name, **kwargs)

    async def close(self) -> None:
        if self.redis is not None:
            await self.redis.aclose(close_connection_pool=True)


job_queue_manager = JobQueueManager()
