"""Tests for PostgreSQL and Redis startup checks."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from shorty.adapters import healthchecks as healthchecks_module
from shorty.adapters.healthchecks import check_storage_connections


def make_engine() -> tuple[MagicMock, AsyncMock]:
    connection = AsyncMock()
    connection_context = MagicMock()
    connection_context.__aenter__ = AsyncMock(return_value=connection)
    connection_context.__aexit__ = AsyncMock(return_value=None)
    engine = MagicMock(spec=AsyncEngine)
    engine.connect.return_value = connection_context
    return engine, connection


def make_redis_client(*, side_effect: object = None) -> MagicMock:
    redis_client = MagicMock(spec=Redis)
    redis_client.ping = AsyncMock(return_value=True, side_effect=side_effect)
    return redis_client


async def test_storage_connections_query_postgres_and_ping_redis(
    caplog: pytest.LogCaptureFixture,
) -> None:
    engine, connection = make_engine()
    redis_client = make_redis_client()

    with caplog.at_level(logging.INFO, logger=healthchecks_module.__name__):
        await check_storage_connections(
            engine,
            redis_client,
            attempts=1,
            retry_delay_seconds=0,
        )

    statement = connection.execute.await_args.args[0]
    assert str(statement) == 'SELECT 1'
    redis_client.ping.assert_awaited_once_with()
    assert caplog.messages == [
        'Postgres connection check succeeded.',
        'Redis connection check succeeded.',
    ]


async def test_storage_connections_retry_after_a_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, _connection = make_engine()
    redis_client = make_redis_client(
        side_effect=[ConnectionError('Redis is starting.'), True],
    )
    sleep = AsyncMock()
    monkeypatch.setattr(healthchecks_module.asyncio, 'sleep', sleep)

    await check_storage_connections(
        engine,
        redis_client,
        attempts=2,
        retry_delay_seconds=0.5,
    )

    assert redis_client.ping.await_count == 2
    sleep.assert_awaited_once_with(0.5)


async def test_storage_connection_failure_aborts_the_check() -> None:
    engine, _connection = make_engine()
    redis_client = make_redis_client(
        side_effect=ConnectionError('Redis is unavailable.'),
    )

    with pytest.raises(ConnectionError, match='Redis is unavailable'):
        await check_storage_connections(
            engine,
            redis_client,
            attempts=1,
            retry_delay_seconds=0,
        )
