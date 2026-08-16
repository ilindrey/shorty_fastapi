"""Fixtures for full-stack e2e tests in the isolated test environment."""

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

from shorty.adapters.orm import metadata
from shorty.config import Settings
from shorty.entrypoints.fastapi_app import create_app


@pytest_asyncio.fixture
async def app() -> AsyncIterator[FastAPI]:
    """Run the app against clean data in the Alembic-managed test schema."""
    settings = Settings()
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(metadata.tables['links'].delete())
    await engine.dispose()

    redis_client = Redis.from_url(settings.redis_url)
    await redis_client.flushdb()
    await redis_client.aclose()

    try:
        fastapi_app = create_app()
        async with fastapi_app.router.lifespan_context(fastapi_app):
            yield fastapi_app
    finally:
        engine = create_async_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.execute(metadata.tables['links'].delete())
        await engine.dispose()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Provide an httpx client bound to `app` over an in-process ASGI transport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as http_client:
        yield http_client
