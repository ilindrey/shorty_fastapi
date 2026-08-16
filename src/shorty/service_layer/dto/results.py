"""Results returned by application use cases."""

from dataclasses import dataclass

from shorty.service_layer.dto.queries import LinkSummary


@dataclass(frozen=True)
class CreatedLink:
    """Result of creating one shortened link."""

    subpart: str
    url: str
    clicks: int = 0


@dataclass(frozen=True)
class LinkPage:
    """One owner-scoped page of shortened links."""

    items: list[LinkSummary]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class PurgeResult:
    """Identifiers deleted by cleanup and those left after retry exhaustion."""

    deleted_subparts: tuple[str, ...]
    failed_subparts: tuple[str, ...]
