"""Fixtures shared by integration tests in the isolated test environment."""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shorty.adapters.orm import metadata, start_mappers
from shorty.config import Settings

start_mappers()


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Provide an engine whose Alembic-managed data is cleared per test."""
    engine = create_async_engine(Settings().database_url)
    async with engine.begin() as conn:
        await conn.execute(metadata.tables['links'].delete())

    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.execute(metadata.tables['links'].delete())
        await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Provide a session factory bound to the per-test `engine` fixture."""
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Redis]:
    """Provide a real Redis client, flushed before and after each test."""
    client = Redis.from_url(Settings().redis_url)
    await client.flushdb()

    yield client

    await client.flushdb()
    await client.aclose()
