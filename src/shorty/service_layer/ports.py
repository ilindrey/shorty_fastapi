"""Plain-Python ports owned by the application layer."""

from __future__ import annotations

import abc
from collections.abc import Iterator
from datetime import datetime
from types import TracebackType

from shorty.domain import events
from shorty.domain.model import Link
from shorty.service_layer.dto import LinkSummary, RedirectTarget


class AbstractRepository(abc.ABC):
    """Port for persisting and retrieving Link aggregates."""

    def __init__(self) -> None:
        """Initialize the aggregates seen during the current unit of work."""
        self.seen: set[Link] = set()

    async def add(self, link: Link) -> None:
        """Persist a new Link."""
        await self._add(link)
        self.seen.add(link)

    async def get(self, subpart: str) -> Link | None:
        """Fetch a Link by its subpart, or None if it does not exist."""
        link = await self._get(subpart)
        if link is not None:
            self.seen.add(link)
        return link

    @abc.abstractmethod
    async def _add(self, link: Link) -> None: ...

    @abc.abstractmethod
    async def _get(self, subpart: str) -> Link | None: ...

    @abc.abstractmethod
    async def delete(self, link: Link) -> None:
        """Remove a Link."""


class AbstractUnitOfWork(abc.ABC):
    """Port for atomically grouping repository operations."""

    links: AbstractRepository

    async def __aenter__(self) -> AbstractUnitOfWork:
        """Enter the unit of work, ready for repository operations."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Roll back any change not explicitly committed before exiting."""
        await self.rollback()

    @abc.abstractmethod
    async def commit(self) -> None:
        """Persist every change made during this unit of work."""

    @abc.abstractmethod
    async def rollback(self) -> None:
        """Discard every uncommitted change."""

    def collect_new_events(self) -> Iterator[events.Event]:
        """Drain and yield events raised by aggregates seen so far."""
        for link in self.links.seen:
            while link.events:
                yield link.events.pop(0)


class AbstractLinkCache(abc.ABC):
    """Port for the redirect cache."""

    @abc.abstractmethod
    async def get(self, subpart: str) -> str | None:
        """Return the cached URL, or None on a cache miss."""

    @abc.abstractmethod
    async def set(self, subpart: str, url: str, ttl_seconds: int) -> None:
        """Cache `url` under `subpart` for `ttl_seconds`."""

    @abc.abstractmethod
    async def delete(self, subpart: str) -> None:
        """Evict `subpart` from the cache."""


class AbstractLinkReadModel(abc.ABC):
    """Port for CQRS reads that do not build domain aggregates."""

    @abc.abstractmethod
    async def get_redirect_target(self, subpart: str) -> RedirectTarget | None:
        """Return redirect data for `subpart`, if it exists."""

    @abc.abstractmethod
    async def list_links(
        self,
        owner_session_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[LinkSummary], int]:
        """Return one owner-scoped page and the total row count."""

    @abc.abstractmethod
    async def list_expired_subparts(
        self,
        cutoff: datetime,
        after: str | None,
        limit: int,
    ) -> list[str]:
        """Return the next keyset page of subparts older than `cutoff`."""
