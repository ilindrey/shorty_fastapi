"""Integration tests for the repository and unit of work, against real Postgres."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shorty.adapters.repository import SqlAlchemyRepository
from shorty.adapters.unit_of_work import SqlAlchemyUnitOfWork
from shorty.domain.events import LinkCreated
from shorty.domain.model import Link
from shorty.exceptions import ConcurrentUpdateError, SubpartAlreadyExistsError

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_add_and_get_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        repo = SqlAlchemyRepository(session)
        link = Link.create(
            subpart='abc123',
            url='https://example.com',
            owner_session_id='s1',
            created_at=NOW,
        )
        await repo.add(link)
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyRepository(session)
        fetched = await repo.get('abc123')

    assert fetched is not None
    assert fetched.url == 'https://example.com'
    assert fetched.owner_session_id == 's1'
    assert fetched.clicks == 0
    # The 'load' mapper event must reinitialize non-column fields on load.
    assert fetched.events == []


async def test_get_missing_subpart_returns_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        repo = SqlAlchemyRepository(session)
        assert await repo.get('missing') is None


async def test_delete_removes_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        repo = SqlAlchemyRepository(session)
        link = Link.create(
            subpart='abc123',
            url='https://example.com',
            owner_session_id='s1',
            created_at=NOW,
        )
        await repo.add(link)
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyRepository(session)
        fetched = await repo.get('abc123')
        assert fetched is not None
        await repo.delete(fetched)
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyRepository(session)
        assert await repo.get('abc123') is None


async def test_unit_of_work_rolls_back_without_commit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uow = SqlAlchemyUnitOfWork(session_factory)
    async with uow:
        link = Link.create(
            subpart='abc123',
            url='https://example.com',
            owner_session_id='s1',
            created_at=NOW,
        )
        await uow.links.add(link)
        # No commit: __aexit__ must roll this back.

    async with session_factory() as session:
        repo = SqlAlchemyRepository(session)
        assert await repo.get('abc123') is None


async def test_unit_of_work_collects_events_after_commit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uow = SqlAlchemyUnitOfWork(session_factory)
    async with uow:
        link = Link.create(
            subpart='abc123',
            url='https://example.com',
            owner_session_id='s1',
            created_at=NOW,
        )
        await uow.links.add(link)
        await uow.commit()
        collected = list(uow.collect_new_events())

    assert len(collected) == 1
    event = collected[0]
    assert isinstance(event, LinkCreated)
    assert event.subpart == 'abc123'


async def test_unit_of_work_rejects_use_outside_context(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uow = SqlAlchemyUnitOfWork(session_factory)

    with pytest.raises(RuntimeError, match='used outside'):
        await uow.rollback()


async def test_optimistic_lock_rejects_second_concurrent_update(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await SqlAlchemyRepository(session).add(
            Link.create('versioned', 'https://example.com', 's1', NOW),
        )
        await session.commit()

    async with (
        SqlAlchemyUnitOfWork(session_factory) as first,
        SqlAlchemyUnitOfWork(session_factory) as second,
    ):
        first_link = await first.links.get('versioned')
        second_link = await second.links.get('versioned')
        assert first_link is not None
        assert second_link is not None
        first_link.record_click()
        second_link.record_click()

        await first.commit()
        with pytest.raises(ConcurrentUpdateError):
            await second.commit()

    async with session_factory() as session:
        stored = await session.get(Link, 'versioned')
        assert stored is not None
        assert stored.clicks == 1
        assert stored.version_number == 1


async def test_optimistic_lock_protects_delete_from_stale_state(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await SqlAlchemyRepository(session).add(
            Link.create('delete-me', 'https://example.com', 's1', NOW),
        )
        await session.commit()

    async with (
        SqlAlchemyUnitOfWork(session_factory) as updater,
        SqlAlchemyUnitOfWork(session_factory) as deleter,
    ):
        updated = await updater.links.get('delete-me')
        stale = await deleter.links.get('delete-me')
        assert updated is not None
        assert stale is not None
        updated.record_click()
        await deleter.links.delete(stale)

        await updater.commit()
        with pytest.raises(ConcurrentUpdateError):
            await deleter.commit()


async def test_unit_of_work_translates_concurrent_duplicate_subpart(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with (
        SqlAlchemyUnitOfWork(session_factory) as first,
        SqlAlchemyUnitOfWork(session_factory) as second,
    ):
        await first.links.add(Link.create('same', 'https://one.example', 's1', NOW))
        await second.links.add(Link.create('same', 'https://two.example', 's2', NOW))

        await first.commit()
        with pytest.raises(SubpartAlreadyExistsError, match='same'):
            await second.commit()


async def test_unit_of_work_does_not_translate_other_integrity_errors(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uow = SqlAlchemyUnitOfWork(session_factory)
    async with uow:
        invalid = Link.create('invalid', 'https://example.com', 's1', NOW)
        invalid.url = None  # type: ignore[assignment]
        await uow.links.add(invalid)

        with pytest.raises(IntegrityError):
            await uow.commit()
