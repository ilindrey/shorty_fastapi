"""Command and event handlers.

Handlers receive a Unit of Work and cache as regular arguments.
`bootstrap.bootstrap_application` binds the adapters with `functools.partial`
before registering each handler with the message bus. Unit tests can replace
these dependencies with fakes.
"""

import logging
from collections.abc import Callable
from datetime import datetime

from shorty.domain import commands, events, model
from shorty.domain.model import Link
from shorty.exceptions import SubpartAlreadyExistsError, SubpartGenerationError
from shorty.service_layer.messagebus import CommandHandler, EventHandler
from shorty.service_layer.ports import AbstractLinkCache, AbstractUnitOfWork

logger = logging.getLogger(__name__)

#: Stop generation from looping forever if the keyspace is unavailable.
_MAX_SUBPART_ATTEMPTS = 10


async def create_link(
    command: commands.CreateLink,
    uow: AbstractUnitOfWork,
    clock: Callable[[], datetime],
    subpart_generator: Callable[[], str],
) -> str:
    """Create a Link, generating a subpart if the caller did not request one.

    Returns the subpart the link was stored under.
    """
    async with uow:
        subpart = await _resolve_subpart(command.subpart, uow, subpart_generator)
        link = Link.create(
            subpart=subpart,
            url=command.url,
            owner_session_id=command.owner_session_id,
            created_at=clock(),
        )
        await uow.links.add(link)
        await uow.commit()
        return subpart


async def _resolve_subpart(
    requested: str | None,
    uow: AbstractUnitOfWork,
    subpart_generator: Callable[[], str],
) -> str:
    """Validate a caller-chosen subpart, or generate a free one."""
    if requested is not None:
        model.validate_subpart(requested)
        if await uow.links.get(requested) is not None:
            raise SubpartAlreadyExistsError(requested)
        return requested

    for _ in range(_MAX_SUBPART_ATTEMPTS):
        candidate = subpart_generator()
        if await uow.links.get(candidate) is None:
            return candidate
    raise SubpartGenerationError(
        'Could not generate a free subpart; keyspace may be exhausted.',
    )


async def record_click(command: commands.RecordClick, uow: AbstractUnitOfWork) -> None:
    """Increment the click counter for a link, ignoring unknown subparts."""
    async with uow:
        link = await uow.links.get(command.subpart)
        if link is None:
            logger.warning('Ignoring click for unknown subpart %r.', command.subpart)
            return
        link.record_click()
        await uow.commit()


async def expire_link(
    command: commands.ExpireLink,
    uow: AbstractUnitOfWork,
) -> bool:
    """Delete one link and report whether it still existed."""
    async with uow:
        link = await uow.links.get(command.subpart)
        if link is None:
            return False
        link.expire()
        await uow.links.delete(link)
        await uow.commit()
        return True


async def cache_link_on_creation(
    event: events.LinkCreated,
    cache: AbstractLinkCache,
    cache_ttl_seconds: int,
) -> None:
    """Write-through the new mapping into the redirect cache."""
    await cache.set(event.subpart, event.url, cache_ttl_seconds)
    logger.info('Cached link %s -> %s', event.subpart, event.url)


async def evict_link_from_cache(
    event: events.LinkExpired,
    cache: AbstractLinkCache,
) -> None:
    """Remove an expired link's mapping from the redirect cache."""
    await cache.delete(event.subpart)
    logger.info('Evicted expired link %s from cache', event.subpart)


EVENT_HANDLERS: dict[type[events.Event], list[EventHandler]] = {
    events.LinkCreated: [cache_link_on_creation],
    events.LinkExpired: [evict_link_from_cache],
}

COMMAND_HANDLERS: dict[type[commands.Command], CommandHandler] = {
    commands.CreateLink: create_link,
    commands.RecordClick: record_click,
    commands.ExpireLink: expire_link,
}
