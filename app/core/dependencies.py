"""Shared dependency providers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import db_manager
from app.core.events import EventBus, event_bus
from app.core.jobs import JobQueueManager, job_queue_manager
from app.core.redis import redis_manager


def get_app_settings() -> Settings:
    return get_settings()


async def get_db_session(_: Settings = Depends(get_app_settings)) -> AsyncIterator[AsyncSession]:
    async for session in db_manager.session():
        yield session


async def get_redis(_: Settings = Depends(get_app_settings)) -> Redis:
    if redis_manager.client is None:
        raise RuntimeError("RedisManager is not configured")
    return redis_manager.client


def get_event_bus() -> EventBus:
    return event_bus


def get_job_queue() -> JobQueueManager:
    return job_queue_manager
