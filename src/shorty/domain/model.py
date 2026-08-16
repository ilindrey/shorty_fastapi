"""The Link aggregate: a plain dataclass with no ORM or infrastructure dependency."""

from __future__ import annotations

import re
import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime

from shorty.domain import events
from shorty.exceptions import InvalidSubpartError

#: Allowed characters and length for both user-chosen and generated subparts.
_SUBPART_PATTERN = re.compile(r'^[A-Za-z0-9_-]{3,32}$')

#: Path segments that would collide with the application's own routes.
RESERVED_SUBPARTS = frozenset(
    {
        'api',
        'docs',
        'redoc',
        'openapi.json',
        'static',
        'health',
        'favicon.ico',
        'links',
    },
)

_GENERATED_ALPHABET = string.ascii_letters + string.digits
_GENERATED_LENGTH = 8


def validate_subpart(subpart: str) -> None:
    """Raise InvalidSubpartError if `subpart` cannot be used as a short link."""
    if subpart in RESERVED_SUBPARTS:
        raise InvalidSubpartError(f'Subpart {subpart!r} is reserved.')
    if not _SUBPART_PATTERN.fullmatch(subpart):
        raise InvalidSubpartError(
            'Subpart must be 3-32 characters long and contain only letters, '
            'digits, "-" or "_".',
        )


def generate_subpart() -> str:
    """Generate a random subpart candidate; caller must still check uniqueness."""
    return ''.join(
        secrets.choice(_GENERATED_ALPHABET) for _ in range(_GENERATED_LENGTH)
    )


@dataclass(eq=False)
class Link:
    """A shortened URL owned by one anonymous browser session.

    `eq=False` keeps the default identity-based `__eq__`/`__hash__` so
    instances can live in the repository's `seen` set (see
    service_layer.ports.AbstractRepository), matching how the Unit of Work
    tracks which aggregates raised events during a transaction.
    """

    subpart: str
    url: str
    owner_session_id: str
    created_at: datetime
    clicks: int = 0
    version_number: int = 0
    events: list[events.Event] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        subpart: str,
        url: str,
        owner_session_id: str,
        created_at: datetime,
    ) -> Link:
        """Create a new Link and record the LinkCreated event it raises."""
        link = cls(
            subpart=subpart,
            url=url,
            owner_session_id=owner_session_id,
            created_at=created_at,
        )
        link.events.append(events.LinkCreated(subpart=subpart, url=url))
        return link

    def record_click(self) -> None:
        """Increment the click counter and optimistic-lock version."""
        self.clicks += 1
        self.version_number += 1

    def expire(self) -> None:
        """Record the LinkExpired event; the caller must still delete the row."""
        self.events.append(events.LinkExpired(subpart=self.subpart))
