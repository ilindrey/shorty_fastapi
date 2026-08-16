"""Tests for the framework-independent application interface."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from fakes import FakeLinkCache, FakeLinkReadModel

from shorty.domain import commands
from shorty.exceptions import ConcurrentUpdateError, SubpartAlreadyExistsError
from shorty.service_layer.application import (
    ApplicationPolicy,
    ShortyApplication,
)
from shorty.service_layer.dto import LinkSummary, PurgeResult, RedirectTarget
from shorty.service_layer.messagebus import Message, MessageBus

NOW = datetime(2026, 1, 15, tzinfo=UTC)


def fixed_clock() -> datetime:
    return NOW


class StubBus(MessageBus):
    """Return or raise one configured result from `handle`."""

    def __init__(self, result: object = None) -> None:
        """Store a result or exception and an empty call log."""
        self.result = result
        self.calls: list[Message] = []

    async def handle(self, message: Message) -> object:
        """Record the message, then return or raise the configured result."""
        self.calls.append(message)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def make_application(
    bus_factory: Callable[[], MessageBus] | None = None,
    *,
    cache: FakeLinkCache | None = None,
    read_model: FakeLinkReadModel | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    cleanup_batch_size: int = 10,
) -> ShortyApplication:
    """Build an application with in-memory ports."""

    def default_bus_factory() -> MessageBus:
        return StubBus()

    policy = ApplicationPolicy(
        default_page_size=10,
        link_ttl_seconds=14 * 24 * 60 * 60,
        cleanup_batch_size=cleanup_batch_size,
        sleep=sleep or asyncio.sleep,
        clock=fixed_clock,
    )
    return ShortyApplication(
        bus_factory or default_bus_factory,
        cache or FakeLinkCache(),
        read_model or FakeLinkReadModel(),
        policy,
    )


async def test_create_link_hides_command_and_returns_result() -> None:
    bus = StubBus('short123')
    application = make_application(lambda: bus)

    result = await application.create_link('https://example.com', 'owner', 'short123')

    assert result.subpart == 'short123'
    assert result.url == 'https://example.com'
    assert result.clicks == 0
    assert bus.calls == [
        commands.CreateLink('https://example.com', 'owner', 'short123'),
    ]


async def test_list_links_uses_configured_default_page_size() -> None:
    read_model = FakeLinkReadModel(
        [('owner', LinkSummary('short123', 'https://example.com', 2))],
    )
    application = make_application(read_model=read_model)

    result = await application.list_links('owner')

    assert result.items == [LinkSummary('short123', 'https://example.com', 2)]
    assert result.page == 1
    assert result.page_size == 10
    assert result.total == 1


async def test_resolve_redirect_returns_cache_hit_without_reading_storage() -> None:
    cache = FakeLinkCache()
    cache.store['cached'] = 'https://cached.example'
    application = make_application(cache=cache)

    assert await application.resolve_redirect('cached') == 'https://cached.example'


async def test_resolve_redirect_repopulates_cache_after_miss() -> None:
    cache = FakeLinkCache()
    read_model = FakeLinkReadModel(
        targets={
            'found': RedirectTarget(
                'https://db.example',
                NOW - timedelta(days=1),
            ),
        },
    )
    application = make_application(cache=cache, read_model=read_model)

    assert await application.resolve_redirect('found') == 'https://db.example'
    assert cache.store == {'found': 'https://db.example'}
    assert cache.ttls == {'found': 13 * 24 * 60 * 60}


async def test_resolve_redirect_rejects_expired_storage_target() -> None:
    read_model = FakeLinkReadModel(
        targets={
            'expired': RedirectTarget(
                'https://expired.example',
                NOW - timedelta(days=15),
            ),
        },
    )
    cache = FakeLinkCache()
    application = make_application(cache=cache, read_model=read_model)

    assert await application.resolve_redirect('expired') is None
    assert cache.store == {}


async def test_resolve_redirect_returns_none_when_unknown() -> None:
    application = make_application()

    assert await application.resolve_redirect('missing') is None


async def test_record_click_retries_three_conflicts_with_exponential_backoff() -> None:
    buses = [
        StubBus(ConcurrentUpdateError()),
        StubBus(ConcurrentUpdateError()),
        StubBus(ConcurrentUpdateError()),
        StubBus(),
    ]
    delays: list[float] = []

    async def record_delay(delay: float) -> None:
        await asyncio.sleep(0)
        delays.append(delay)

    application = make_application(lambda: buses.pop(0), sleep=record_delay)

    await application.record_click('short123')

    assert delays == [0.01, 0.02, 0.04]
    assert buses == []


async def test_concurrency_error_escapes_after_three_retries() -> None:
    buses = [StubBus(ConcurrentUpdateError()) for _ in range(4)]

    async def no_sleep(_delay: float) -> None:
        await asyncio.sleep(0)

    application = make_application(lambda: buses.pop(0), sleep=no_sleep)

    with pytest.raises(ConcurrentUpdateError):
        await application.record_click('short123')

    assert buses == []


async def test_purge_expired_links_pages_and_returns_deleted_identifiers() -> None:
    read_model = FakeLinkReadModel(
        targets={
            'old-a': RedirectTarget('https://a.example', NOW - timedelta(days=30)),
            'old-b': RedirectTarget('https://b.example', NOW - timedelta(days=20)),
            'fresh': RedirectTarget('https://fresh.example', NOW),
        },
    )
    buses = [StubBus(result=True), StubBus(result=True)]
    application = make_application(
        lambda: buses.pop(0),
        read_model=read_model,
        cleanup_batch_size=1,
    )

    result = await application.purge_expired_links(14)

    assert result == PurgeResult(('old-a', 'old-b'), ())
    assert buses == []


async def test_purge_ignores_link_already_deleted_after_reading() -> None:
    read_model = FakeLinkReadModel(
        targets={
            'already-gone': RedirectTarget(
                'https://gone.example',
                NOW - timedelta(days=30),
            ),
        },
    )
    application = make_application(
        lambda: StubBus(result=False),
        read_model=read_model,
    )

    result = await application.purge_expired_links(14)

    assert result == PurgeResult((), ())


async def test_purge_continues_after_one_link_exhausts_concurrency_retries() -> None:
    read_model = FakeLinkReadModel(
        targets={
            'old-a': RedirectTarget('https://a.example', NOW - timedelta(days=30)),
            'old-b': RedirectTarget('https://b.example', NOW - timedelta(days=20)),
        },
    )
    buses = [StubBus(ConcurrentUpdateError()) for _ in range(4)] + [
        StubBus(result=True),
    ]

    async def no_sleep(_delay: float) -> None:
        await asyncio.sleep(0)

    application = make_application(
        lambda: buses.pop(0),
        read_model=read_model,
        sleep=no_sleep,
    )

    result = await application.purge_expired_links(14)

    assert result == PurgeResult(('old-b',), ('old-a',))


async def test_generated_subpart_collision_retries_with_a_fresh_bus() -> None:
    buses = [StubBus(SubpartAlreadyExistsError('first')), StubBus('second')]
    application = make_application(lambda: buses.pop(0))

    result = await application.create_link('https://example.com', 'owner')

    assert result.subpart == 'second'
    assert buses == []


async def test_requested_subpart_collision_is_not_retried() -> None:
    buses = [StubBus(SubpartAlreadyExistsError('mine'))]
    application = make_application(lambda: buses.pop(0))

    with pytest.raises(SubpartAlreadyExistsError):
        await application.create_link('https://example.com', 'owner', 'mine')

    assert buses == []
