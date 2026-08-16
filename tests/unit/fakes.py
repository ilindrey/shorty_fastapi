"""In-memory fakes for the ports, used to unit-test the service layer without I/O."""

from datetime import datetime

from shorty.domain.model import Link
from shorty.service_layer.dto import LinkSummary, RedirectTarget
from shorty.service_layer.ports import (
    AbstractLinkCache,
    AbstractLinkReadModel,
    AbstractRepository,
    AbstractUnitOfWork,
)


class FakeRepository(AbstractRepository):
    """In-memory stand-in for SqlAlchemyRepository."""

    def __init__(self, links: list[Link] | None = None) -> None:
        """Seed the fake store with any initial links."""
        super().__init__()
        self._links = {link.subpart: link for link in links or []}

    async def _add(self, link: Link) -> None:
        self._links[link.subpart] = link

    async def _get(self, subpart: str) -> Link | None:
        return self._links.get(subpart)

    async def delete(self, link: Link) -> None:
        """Remove a Link."""
        del self._links[link.subpart]


class FakeUnitOfWork(AbstractUnitOfWork):
    """In-memory stand-in for SqlAlchemyUnitOfWork; commit is a no-op flag."""

    def __init__(self, links: list[Link] | None = None) -> None:
        """Seed the fake repository with any initial links."""
        self.links = FakeRepository(links)
        self.committed = False

    async def commit(self) -> None:
        """Record that a commit happened, without touching any real storage."""
        self.committed = True

    async def rollback(self) -> None:
        """No-op: nothing written outside `links` needs discarding."""


class FakeLinkCache(AbstractLinkCache):
    """In-memory stand-in for RedisLinkCache."""

    def __init__(self) -> None:
        """Start with an empty cache."""
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, subpart: str) -> str | None:
        """Return the cached url for `subpart`, or None on a cache miss."""
        return self.store.get(subpart)

    async def set(self, subpart: str, url: str, ttl_seconds: int) -> None:
        """Cache `url` under `subpart`."""
        self.store[subpart] = url
        self.ttls[subpart] = ttl_seconds

    async def delete(self, subpart: str) -> None:
        """Evict `subpart` from the cache."""
        self.store.pop(subpart, None)
        self.ttls.pop(subpart, None)


class FakeLinkReadModel(AbstractLinkReadModel):
    """In-memory CQRS read adapter."""

    def __init__(
        self,
        rows: list[tuple[str, LinkSummary]] | None = None,
        targets: dict[str, RedirectTarget] | None = None,
    ) -> None:
        """Seed owner-scoped summaries and redirect targets."""
        self.rows = rows or []
        self.targets = targets or {}

    async def get_redirect_target(self, subpart: str) -> RedirectTarget | None:
        """Return configured redirect data."""
        return self.targets.get(subpart)

    async def list_links(
        self,
        owner_session_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[LinkSummary], int]:
        """Return an owner-scoped in-memory page."""
        owned = [row for owner, row in self.rows if owner == owner_session_id]
        start = (page - 1) * page_size
        return owned[start : start + page_size], len(owned)

    async def list_expired_subparts(
        self,
        cutoff: datetime,
        after: str | None,
        limit: int,
    ) -> list[str]:
        """Return an expired keyset page from configured targets."""
        subparts = sorted(
            subpart
            for subpart, target in self.targets.items()
            if target.created_at < cutoff and (after is None or subpart > after)
        )
        return subparts[:limit]
