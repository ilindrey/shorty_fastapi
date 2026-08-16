"""Unit tests for the Link aggregate and subpart validation rules."""

from datetime import UTC, datetime

import pytest

from shorty.domain import events
from shorty.domain.model import (
    Link,
    generate_subpart,
    validate_subpart,
)
from shorty.exceptions import InvalidSubpartError

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_create_raises_link_created_event() -> None:
    link = Link.create(
        subpart='abc123',
        url='https://example.com',
        owner_session_id='s1',
        created_at=NOW,
    )

    assert link.clicks == 0
    assert link.events == [
        events.LinkCreated(subpart='abc123', url='https://example.com'),
    ]


def test_record_click_increments_clicks_and_version() -> None:
    link = Link.create(
        subpart='abc123',
        url='https://example.com',
        owner_session_id='s1',
        created_at=NOW,
    )
    link.events.clear()

    link.record_click()

    assert link.clicks == 1
    assert link.version_number == 1
    assert link.events == []


def test_expire_raises_event_without_deleting() -> None:
    link = Link.create(
        subpart='abc123',
        url='https://example.com',
        owner_session_id='s1',
        created_at=NOW,
    )
    link.events.clear()

    link.expire()

    assert link.events == [events.LinkExpired(subpart='abc123')]


@pytest.mark.parametrize(
    'subpart',
    ['abc', 'a-b_c', 'A1' * 16],
)
def test_validate_subpart_accepts_well_formed_values(subpart: str) -> None:
    validate_subpart(subpart)


@pytest.mark.parametrize(
    'subpart',
    ['ab', 'a' * 33, 'has space', 'has/slash', 'api', 'docs'],
)
def test_validate_subpart_rejects_bad_values(subpart: str) -> None:
    with pytest.raises(InvalidSubpartError):
        validate_subpart(subpart)


def test_generate_subpart_is_well_formed() -> None:
    subpart = generate_subpart()

    validate_subpart(subpart)
    assert len(subpart) == 8
