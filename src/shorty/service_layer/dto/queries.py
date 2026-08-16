"""Read-side projections returned by query ports."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LinkSummary:
    """Read-only summary of one shortened link."""

    subpart: str
    url: str
    clicks: int


@dataclass(frozen=True)
class RedirectTarget:
    """Destination and creation time used to enforce absolute link expiry."""

    url: str
    created_at: datetime
