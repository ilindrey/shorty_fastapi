"""Configure and run the application's database migrations."""

import asyncio
import logging

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from shorty.adapters.orm import metadata, start_mappers
from shorty.config import Settings

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)-5.5s [%(name)s] %(message)s',
)
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

# Register mappings so Alembic autogenerate can inspect the domain model.
start_mappers()
target_metadata = metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configure Alembic with a URL and emit SQL without creating an engine or
    requiring a DBAPI driver.
    """
    context.configure(
        url=Settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations through an existing synchronous connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an asynchronous engine.

    Alembic executes its synchronous migration operations through the
    connection's `run_sync` bridge.
    """
    connectable = create_async_engine(
        Settings().database_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
