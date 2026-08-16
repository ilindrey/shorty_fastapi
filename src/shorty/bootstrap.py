"""Composition root for the application and its adapters."""

import inspect
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import cast

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shorty.adapters.healthchecks import check_storage_connections
from shorty.adapters.orm import start_mappers
from shorty.adapters.read_model import SqlAlchemyLinkReadModel
from shorty.adapters.redis_cache import RedisLinkCache
from shorty.adapters.unit_of_work import SqlAlchemyUnitOfWork
from shorty.config import Settings
from shorty.domain import model
from shorty.service_layer import handlers
from shorty.service_layer.application import (
    ApplicationPolicy,
    ShortyApplication,
    utc_now,
)
from shorty.service_layer.messagebus import (
    CommandHandler,
    EventHandler,
    MessageBus,
)
from shorty.service_layer.ports import (
    AbstractLinkCache,
    AbstractLinkReadModel,
    AbstractUnitOfWork,
)

Handler = CommandHandler | EventHandler


def _inject_dependencies(
    handler: Handler,
    dependencies: dict[str, object],
) -> Handler:
    """Bind only dependencies explicitly declared by `handler`."""
    parameters = inspect.signature(handler).parameters
    selected = {
        name: value for name, value in dependencies.items() if name in parameters
    }
    return cast('Handler', partial(handler, **selected))


@dataclass(frozen=True)
class BootstrapOverrides:
    """Optional adapters and deterministic functions used by tests."""

    uow_factory: Callable[[], AbstractUnitOfWork] | None = None
    read_model: AbstractLinkReadModel | None = None
    clock: Callable[[], datetime] = utc_now
    subpart_generator: Callable[[], str] = model.generate_subpart
    start_orm: bool = True


def bootstrap_application(
    session_factory: async_sessionmaker[AsyncSession] | None,
    cache: AbstractLinkCache,
    settings: Settings,
    overrides: BootstrapOverrides | None = None,
) -> ShortyApplication:
    """Build the application interface with fresh transactional state per command."""
    selected = overrides or BootstrapOverrides()
    if selected.start_orm:
        start_mappers()
    if session_factory is None and (
        selected.uow_factory is None or selected.read_model is None
    ):
        raise ValueError(
            'session_factory is required unless all storage ports are set.'
        )

    def default_uow_factory() -> AbstractUnitOfWork:
        if session_factory is None:  # pragma: no cover - guarded above
            raise AssertionError
        return SqlAlchemyUnitOfWork(session_factory)

    make_uow = selected.uow_factory or default_uow_factory
    link_reads = selected.read_model or SqlAlchemyLinkReadModel(
        cast('async_sessionmaker[AsyncSession]', session_factory),
    )

    def make_bus() -> MessageBus:
        uow = make_uow()
        dependencies: dict[str, object] = {
            'uow': uow,
            'cache': cache,
            'clock': selected.clock,
            'subpart_generator': selected.subpart_generator,
            'cache_ttl_seconds': settings.link_ttl_seconds,
        }
        event_handlers: dict[type, list[EventHandler]] = {
            event_type: [
                cast('EventHandler', _inject_dependencies(handler, dependencies))
                for handler in handler_list
            ]
            for event_type, handler_list in handlers.EVENT_HANDLERS.items()
        }
        command_handlers: dict[type, CommandHandler] = {
            command_type: cast(
                'CommandHandler',
                _inject_dependencies(handler, dependencies),
            )
            for command_type, handler in handlers.COMMAND_HANDLERS.items()
        }
        return MessageBus(uow, event_handlers, command_handlers)

    return ShortyApplication(
        make_bus,
        cache,
        link_reads,
        ApplicationPolicy(
            default_page_size=settings.page_size,
            link_ttl_seconds=settings.link_ttl_seconds,
            cleanup_batch_size=settings.cleanup_batch_size,
            clock=selected.clock,
        ),
    )


@asynccontextmanager
async def application_runtime(settings: Settings) -> AsyncIterator[ShortyApplication]:
    """Create and close the infrastructure used by an entrypoint."""
    engine = create_async_engine(
        settings.database_url,
        connect_args={'timeout': settings.postgres_connection_timeout_seconds},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=settings.redis_connection_timeout_seconds,
        socket_timeout=settings.redis_connection_timeout_seconds,
    )
    cache = RedisLinkCache(redis_client)
    try:
        await check_storage_connections(
            engine,
            redis_client,
            settings.startup_connection_attempts,
            settings.startup_connection_retry_delay_seconds,
        )
        yield bootstrap_application(session_factory, cache, settings)
    finally:
        await redis_client.aclose()
        await engine.dispose()
