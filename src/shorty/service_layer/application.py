"""Application interface used by the HTTP and scheduler entrypoints."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import cast

from shorty.domain import commands
from shorty.exceptions import ConcurrentUpdateError, SubpartAlreadyExistsError
from shorty.service_layer.dto import CreatedLink, LinkPage, PurgeResult
from shorty.service_layer.messagebus import MessageBus
from shorty.service_layer.ports import AbstractLinkCache, AbstractLinkReadModel

logger = logging.getLogger(__name__)

_MAX_CONCURRENT_RETRIES = 3
_MAX_GENERATED_SUBPART_RETRIES = 3
_INITIAL_RETRY_DELAY_SECONDS = 0.01


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class ApplicationPolicy:
    """Runtime policies and replaceable time/backoff functions."""

    default_page_size: int
    link_ttl_seconds: int
    cleanup_batch_size: int
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    clock: Callable[[], datetime] = utc_now


class ShortyApplication:
    """Application API for link creation, lookup, clicks, and cleanup."""

    def __init__(
        self,
        bus_factory: Callable[[], MessageBus],
        cache: AbstractLinkCache,
        read_model: AbstractLinkReadModel,
        policy: ApplicationPolicy,
    ) -> None:
        """Bind application ports and retry policy."""
        self._bus_factory = bus_factory
        self._cache = cache
        self._read_model = read_model
        self._policy = policy

    async def create_link(
        self,
        url: str,
        owner_session_id: str,
        subpart: str | None = None,
    ) -> CreatedLink:
        """Create a shortened link."""
        command = commands.CreateLink(
            url=url,
            owner_session_id=owner_session_id,
            subpart=subpart,
        )
        generated_retry = 0
        while True:
            try:
                created_subpart = cast('str', await self._handle_with_retry(command))
                break
            except SubpartAlreadyExistsError:
                if (
                    subpart is not None
                    or generated_retry == _MAX_GENERATED_SUBPART_RETRIES
                ):
                    raise
                generated_retry += 1
        return CreatedLink(subpart=created_subpart, url=url)

    async def list_links(
        self,
        owner_session_id: str,
        page: int = 1,
        page_size: int | None = None,
    ) -> LinkPage:
        """Return one page of the caller's links."""
        effective_page_size = page_size or self._policy.default_page_size
        rows, total = await self._read_model.list_links(
            owner_session_id,
            page,
            effective_page_size,
        )
        return LinkPage(rows, page, effective_page_size, total)

    async def resolve_redirect(self, subpart: str) -> str | None:
        """Resolve a URL through the cache-aside read path."""
        url = await self._cache.get(subpart)
        if url is not None:
            return url
        target = await self._read_model.get_redirect_target(subpart)
        if target is not None:
            expires_at = target.created_at + timedelta(
                seconds=self._policy.link_ttl_seconds,
            )
            ttl_seconds = ceil((expires_at - self._policy.clock()).total_seconds())
            if ttl_seconds <= 0:
                return None
            logger.info('Cache miss for %s; repopulating from Postgres.', subpart)
            await self._cache.set(subpart, target.url, ttl_seconds)
            return target.url
        return None

    async def record_click(self, subpart: str) -> None:
        """Record one redirect click, retrying optimistic-lock conflicts."""
        await self._handle_with_retry(commands.RecordClick(subpart=subpart))

    async def purge_expired_links(self, older_than_days: int) -> PurgeResult:
        """Delete expired links in keyset pages and one transaction per aggregate."""
        cutoff = self._policy.clock() - timedelta(days=older_than_days)
        after: str | None = None
        deleted: list[str] = []
        failed: list[str] = []
        while True:
            subparts = await self._read_model.list_expired_subparts(
                cutoff,
                after,
                self._policy.cleanup_batch_size,
            )
            if not subparts:
                break
            for subpart in subparts:
                try:
                    was_deleted = cast(
                        'bool',
                        await self._handle_with_retry(commands.ExpireLink(subpart)),
                    )
                except ConcurrentUpdateError:
                    failed.append(subpart)
                else:
                    if was_deleted:
                        deleted.append(subpart)
            after = subparts[-1]
        return PurgeResult(tuple(deleted), tuple(failed))

    async def _handle_with_retry(self, command: commands.Command) -> object:
        retry = 0
        while True:
            try:
                return await self._bus_factory().handle(command)
            except ConcurrentUpdateError:
                if retry == _MAX_CONCURRENT_RETRIES:
                    logger.exception(
                        'Concurrent update retries exhausted for %r.',
                        command,
                    )
                    raise
                delay = _INITIAL_RETRY_DELAY_SECONDS * (2**retry)
                logger.warning(
                    'Concurrent update for %r; retrying in %.3fs.',
                    command,
                    delay,
                )
                await self._policy.sleep(delay)
                retry += 1
