"""Unit tests for the command/event handlers, run against fakes only (no I/O)."""

from datetime import UTC, datetime

import pytest
from fakes import FakeLinkCache, FakeUnitOfWork

from shorty.domain import commands, events
from shorty.domain.model import Link
from shorty.exceptions import SubpartAlreadyExistsError, SubpartGenerationError
from shorty.service_layer import handlers

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def fixed_clock() -> datetime:
    return NOW


def generated_subpart() -> str:
    return 'generated'


async def test_create_link_with_explicit_subpart() -> None:
    uow = FakeUnitOfWork()

    subpart = await handlers.create_link(
        commands.CreateLink(
            url='https://example.com',
            owner_session_id='s1',
            subpart='mine',
        ),
        uow,
        fixed_clock,
        generated_subpart,
    )

    assert subpart == 'mine'
    assert uow.committed
    stored = await uow.links.get('mine')
    assert stored is not None
    assert stored.url == 'https://example.com'


async def test_create_link_generates_subpart_when_not_requested() -> None:
    uow = FakeUnitOfWork()

    subpart = await handlers.create_link(
        commands.CreateLink(url='https://example.com', owner_session_id='s1'),
        uow,
        fixed_clock,
        generated_subpart,
    )

    assert subpart == 'generated'
    assert await uow.links.get(subpart) is not None


async def test_create_link_rejects_taken_subpart() -> None:
    existing = Link.create(
        subpart='taken',
        url='https://example.com',
        owner_session_id='s1',
        created_at=NOW,
    )
    uow = FakeUnitOfWork(links=[existing])

    with pytest.raises(SubpartAlreadyExistsError):
        await handlers.create_link(
            commands.CreateLink(
                url='https://example.com/other',
                owner_session_id='s2',
                subpart='taken',
            ),
            uow,
            fixed_clock,
            generated_subpart,
        )


async def test_create_link_fails_when_generated_keyspace_is_exhausted() -> None:
    existing = Link.create(
        subpart='collision',
        url='https://example.com',
        owner_session_id='s1',
        created_at=NOW,
    )
    uow = FakeUnitOfWork(links=[existing])

    def collide() -> str:
        return 'collision'

    with pytest.raises(SubpartGenerationError, match='keyspace may be exhausted'):
        await handlers.create_link(
            commands.CreateLink(url='https://example.com/new', owner_session_id='s2'),
            uow,
            fixed_clock,
            collide,
        )


async def test_record_click_increments_existing_link() -> None:
    link = Link.create(
        subpart='abc',
        url='https://example.com',
        owner_session_id='s1',
        created_at=NOW,
    )
    uow = FakeUnitOfWork(links=[link])

    await handlers.record_click(commands.RecordClick(subpart='abc'), uow)

    stored = await uow.links.get('abc')
    assert stored is not None
    assert stored.clicks == 1
    assert uow.committed


async def test_record_click_ignores_unknown_subpart() -> None:
    uow = FakeUnitOfWork()

    await handlers.record_click(commands.RecordClick(subpart='missing'), uow)

    assert not uow.committed


async def test_expire_link_deletes_existing_link() -> None:
    link = Link.create(
        subpart='old',
        url='https://example.com',
        owner_session_id='s1',
        created_at=NOW,
    )
    uow = FakeUnitOfWork(links=[link])

    deleted = await handlers.expire_link(
        commands.ExpireLink(subpart='old'),
        uow,
    )

    assert deleted is True
    assert await uow.links.get('old') is None


async def test_expire_link_is_idempotent_when_link_is_missing() -> None:
    uow = FakeUnitOfWork()

    deleted = await handlers.expire_link(commands.ExpireLink('missing'), uow)

    assert deleted is False
    assert not uow.committed


async def test_cache_link_on_creation_writes_through() -> None:
    cache = FakeLinkCache()

    await handlers.cache_link_on_creation(
        events.LinkCreated(subpart='abc', url='https://example.com'),
        cache,
        60,
    )

    assert cache.store == {'abc': 'https://example.com'}
    assert cache.ttls == {'abc': 60}


async def test_evict_link_from_cache_removes_entry() -> None:
    cache = FakeLinkCache()
    cache.store['abc'] = 'https://example.com'

    await handlers.evict_link_from_cache(events.LinkExpired(subpart='abc'), cache)

    assert 'abc' not in cache.store
