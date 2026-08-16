"""Integration tests for the SQLAlchemy CQRS read-model adapter."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shorty.adapters.orm import links_table
from shorty.adapters.read_model import SqlAlchemyLinkReadModel


async def _insert_link(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    subpart: str,
    owner_session_id: str,
    created_at: datetime,
) -> None:
    async with session_factory() as session:
        await session.execute(
            links_table.insert().values(
                subpart=subpart,
                url=f'https://example.com/{subpart}',
                owner_session_id=owner_session_id,
                created_at=created_at,
                clicks=0,
            ),
        )
        await session.commit()


async def test_list_links_scopes_to_owner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    await _insert_link(
        session_factory,
        subpart='mine',
        owner_session_id='s1',
        created_at=now,
    )
    await _insert_link(
        session_factory,
        subpart='theirs',
        owner_session_id='s2',
        created_at=now,
    )

    read_model = SqlAlchemyLinkReadModel(session_factory)
    rows, total = await read_model.list_links('s1', page=1, page_size=10)

    assert total == 1
    assert [row.subpart for row in rows] == ['mine']


async def test_list_links_orders_newest_first(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    await _insert_link(
        session_factory,
        subpart='older',
        owner_session_id='s1',
        created_at=now - timedelta(days=1),
    )
    await _insert_link(
        session_factory,
        subpart='newer',
        owner_session_id='s1',
        created_at=now,
    )

    read_model = SqlAlchemyLinkReadModel(session_factory)
    rows, _total = await read_model.list_links('s1', page=1, page_size=10)

    assert [row.subpart for row in rows] == ['newer', 'older']


async def test_list_links_paginates(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    for i in range(15):
        await _insert_link(
            session_factory,
            subpart=f'link{i:02d}',
            owner_session_id='s1',
            created_at=now - timedelta(seconds=i),
        )

    read_model = SqlAlchemyLinkReadModel(session_factory)
    page1, total = await read_model.list_links('s1', page=1, page_size=10)
    page2, _ = await read_model.list_links('s1', page=2, page_size=10)

    assert total == 15
    assert len(page1) == 10
    assert len(page2) == 5
    assert {row.subpart for row in page1} & {row.subpart for row in page2} == set()


async def test_get_redirect_target_returns_destination_and_creation_time(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    created_at = datetime.now(UTC)
    await _insert_link(
        session_factory,
        subpart='lookup',
        owner_session_id='s1',
        created_at=created_at,
    )
    read_model = SqlAlchemyLinkReadModel(session_factory)

    target = await read_model.get_redirect_target('lookup')
    assert target is not None
    assert target.url == 'https://example.com/lookup'
    assert target.created_at == created_at
    assert await read_model.get_redirect_target('missing') is None


async def test_list_expired_subparts_uses_stable_keyset_pages(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    for subpart in ('old-c', 'old-a', 'old-b'):
        await _insert_link(
            session_factory,
            subpart=subpart,
            owner_session_id='s1',
            created_at=now - timedelta(days=30),
        )
    await _insert_link(
        session_factory,
        subpart='fresh',
        owner_session_id='s1',
        created_at=now,
    )
    read_model = SqlAlchemyLinkReadModel(session_factory)

    first = await read_model.list_expired_subparts(
        now - timedelta(days=14),
        after=None,
        limit=2,
    )
    second = await read_model.list_expired_subparts(
        now - timedelta(days=14),
        after=first[-1],
        limit=2,
    )

    assert first == ['old-a', 'old-b']
    assert second == ['old-c']
