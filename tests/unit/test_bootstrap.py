"""Tests for composition-root wiring."""

from datetime import UTC, datetime

import pytest
from fakes import FakeLinkCache, FakeLinkReadModel, FakeUnitOfWork

from shorty.bootstrap import BootstrapOverrides, bootstrap_application
from shorty.config import Settings

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_bootstrap_routes_command_and_event_through_fakes() -> None:
    cache = FakeLinkCache()
    uows: list[FakeUnitOfWork] = []

    def make_uow() -> FakeUnitOfWork:
        uow = FakeUnitOfWork()
        uows.append(uow)
        return uow

    application = bootstrap_application(
        None,
        cache,
        Settings(link_ttl_days=2),
        BootstrapOverrides(
            uow_factory=make_uow,
            read_model=FakeLinkReadModel(),
            clock=lambda: NOW,
            subpart_generator=lambda: 'fromfake',
            start_orm=False,
        ),
    )

    created = await application.create_link('https://example.com', 'owner')

    assert created.subpart == 'fromfake'
    assert cache.store == {'fromfake': 'https://example.com'}
    assert cache.ttls == {'fromfake': 2 * 24 * 60 * 60}
    stored = await uows[0].links.get('fromfake')
    assert stored is not None
    assert stored.created_at == NOW


def test_bootstrap_requires_defaults_or_storage_overrides() -> None:
    with pytest.raises(ValueError, match='session_factory is required'):
        bootstrap_application(
            None,
            FakeLinkCache(),
            Settings(),
            BootstrapOverrides(start_orm=False),
        )
