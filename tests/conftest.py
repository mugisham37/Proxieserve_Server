from __future__ import annotations

import importlib
import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from app.core.config import get_settings
from app.core.database import Base, db_manager
from app.core.redis import redis_manager


@pytest.fixture(scope="session")
def container_env() -> Iterator[dict[str, Any]]:
    with PostgresContainer("postgres:16") as postgres, RedisContainer("redis:7") as redis:
        os.environ["APP_ENV"] = "test"
        os.environ["APP_DEBUG"] = "false"
        os.environ["APP_CORS_ORIGINS"] = "[\"http://localhost:3000\"]"
        os.environ["POSTGRES_HOST"] = postgres.get_container_host_ip()
        os.environ["POSTGRES_PORT"] = str(postgres.get_exposed_port(5432))
        os.environ["POSTGRES_DB"] = postgres.dbname
        os.environ["POSTGRES_USER"] = postgres.username
        os.environ["POSTGRES_PASSWORD"] = postgres.password
        redis_host = redis.get_container_host_ip()
        redis_port = redis.get_exposed_port(6379)
        os.environ["REDIS_URL"] = f"redis://{redis_host}:{redis_port}/0"
        os.environ["JWT_ISSUER"] = "proxiserve-server"
        os.environ["JWT_AUDIENCE"] = "proxiserve-web"
        os.environ["JWT_ACCESS_SECRET"] = "test-access-secret-key-1234567890"
        os.environ["JWT_REFRESH_SECRET"] = "test-refresh-secret-key-123456789"
        os.environ["JWT_PRE_2FA_SECRET"] = "test-pre2fa-secret-key-123456789"
        os.environ["FERNET_SECRET"] = "test-fernet-secret-key-1234567890"
        os.environ["COOKIE_SECURE"] = "false"
        get_settings.cache_clear()
        yield {"postgres": postgres, "redis": redis}


@pytest_asyncio.fixture(scope="session")
async def app(container_env: dict[str, Any]) -> AsyncIterator[FastAPI]:
    settings = get_settings()
    setup_engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    async with setup_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    main_module = importlib.import_module("app.main")
    application = main_module.create_app(settings)
    yield application

    async with setup_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await setup_engine.dispose()
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
            yield async_client


@pytest_asyncio.fixture(autouse=True)
async def reset_state(client: httpx.AsyncClient) -> AsyncIterator[None]:
    assert db_manager.session_factory is not None
    async with db_manager.session_factory() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(delete(table))
        await session.commit()
    if redis_manager.client is not None:
        await redis_manager.client.flushdb()
    yield


@pytest_asyncio.fixture
async def db_session(client: httpx.AsyncClient) -> AsyncIterator[AsyncSession]:
    assert db_manager.session_factory is not None
    session_factory = db_manager.session_factory
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def session_factory() -> async_sessionmaker[AsyncSession]:
    assert db_manager.session_factory is not None
    return db_manager.session_factory
