"""Startup connection checks for PostgreSQL and Redis."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

ConnectionCheck = Callable[[], Awaitable[object]]
logger = logging.getLogger(__name__)


async def _retry_connection_check(
    name: str,
    check: ConnectionCheck,
    retryable_errors: tuple[type[Exception], ...],
    attempts: int,
    retry_delay_seconds: float,
) -> None:
    attempt = 1
    while True:
        try:
            await check()
        except retryable_errors:
            if attempt >= attempts:
                raise
            logger.warning(
                '%s connection check failed; retrying in %s seconds (%s/%s).',
                name,
                retry_delay_seconds,
                attempt,
                attempts,
            )
            await asyncio.sleep(retry_delay_seconds)
            attempt += 1
        else:
            logger.info('%s connection check succeeded.', name)
            return


async def _check_postgres_connection(
    engine: AsyncEngine,
    attempts: int,
    retry_delay_seconds: float,
) -> None:
    async def query_postgres() -> None:
        async with engine.connect() as connection:
            await connection.execute(text('SELECT 1'))

    await _retry_connection_check(
        'Postgres',
        query_postgres,
        (OSError, SQLAlchemyError),
        attempts,
        retry_delay_seconds,
    )


async def _check_redis_connection(
    redis_client: Redis,
    attempts: int,
    retry_delay_seconds: float,
) -> None:
    async def ping_redis() -> None:
        await redis_client.ping()

    await _retry_connection_check(
        'Redis',
        ping_redis,
        (OSError, RedisError),
        attempts,
        retry_delay_seconds,
    )


async def check_storage_connections(
    engine: AsyncEngine,
    redis_client: Redis,
    attempts: int,
    retry_delay_seconds: float,
) -> None:
    """Check each storage connection, retrying transient failures."""
    await _check_postgres_connection(engine, attempts, retry_delay_seconds)
    await _check_redis_connection(redis_client, attempts, retry_delay_seconds)
