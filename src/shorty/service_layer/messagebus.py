"""In-process message bus: routes commands to one handler, events to many.

Command failures propagate to the caller. Event handler failures are logged
and suppressed, so a failed side effect such as a cache write does not roll
back the use case that emitted the event.
"""

import logging
from collections.abc import Awaitable, Callable

from shorty.domain import commands, events
from shorty.service_layer.ports import AbstractUnitOfWork

logger = logging.getLogger(__name__)

Message = commands.Command | events.Event
EventHandler = Callable[..., Awaitable[None]]
CommandHandler = Callable[..., Awaitable[object]]


class MessageBus:
    """Dispatches commands and events to their registered, dependency-bound handlers."""

    def __init__(
        self,
        uow: AbstractUnitOfWork,
        event_handlers: dict[type[events.Event], list[EventHandler]],
        command_handlers: dict[type[commands.Command], CommandHandler],
    ) -> None:
        """Bind the Unit of Work and the handler registries used for dispatch."""
        self.uow = uow
        self.event_handlers = event_handlers
        self.command_handlers = command_handlers

    async def handle(self, message: Message) -> object:
        """Handle `message`, then keep draining any events it caused, breadth-first."""
        queue: list[Message] = [message]
        result: object = None
        while queue:
            current = queue.pop(0)
            if isinstance(current, events.Event):
                await self._handle_event(current, queue)
            elif isinstance(current, commands.Command):
                result = await self._handle_command(current, queue)
            else:
                raise TypeError(f'{current!r} was not an Event or a Command')
        return result

    async def _handle_event(self, event: events.Event, queue: list[Message]) -> None:
        for handler in self.event_handlers.get(type(event), []):
            try:
                await handler(event)
            except Exception:
                logger.exception('Exception handling event %r with %r', event, handler)
                continue
            queue.extend(self.uow.collect_new_events())

    async def _handle_command(
        self,
        command: commands.Command,
        queue: list[Message],
    ) -> object:
        handler = self.command_handlers[type(command)]
        try:
            result = await handler(command)
        except Exception:
            logger.exception('Exception handling command %r', command)
            raise
        queue.extend(self.uow.collect_new_events())
        return result
