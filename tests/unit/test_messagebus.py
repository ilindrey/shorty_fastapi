"""Unit tests for MessageBus dispatch semantics: fan-out, isolation, propagation."""

from typing import cast

import pytest
from fakes import FakeUnitOfWork

from shorty.domain import commands, events
from shorty.service_layer.messagebus import Message, MessageBus


class _PingCommand(commands.Command):
    """A trivial command used only to exercise the bus in isolation."""


class _PingedEvent(events.Event):
    """A trivial event used only to exercise the bus in isolation."""


async def test_event_handlers_all_run_even_if_one_fails() -> None:
    calls: list[str] = []

    async def failing(_event: events.Event) -> None:
        calls.append('failing')
        raise ValueError('boom')

    async def succeeding(_event: events.Event) -> None:
        calls.append('succeeding')

    bus = MessageBus(
        uow=FakeUnitOfWork(),
        event_handlers={_PingedEvent: [failing, succeeding]},
        command_handlers={},
    )

    await bus.handle(_PingedEvent())

    assert calls == ['failing', 'succeeding']


async def test_command_handler_failure_propagates() -> None:
    async def failing(_command: commands.Command) -> None:
        raise ValueError('boom')

    bus = MessageBus(
        uow=FakeUnitOfWork(),
        event_handlers={},
        command_handlers={_PingCommand: failing},
    )

    with pytest.raises(ValueError, match='boom'):
        await bus.handle(_PingCommand())


async def test_command_result_is_returned() -> None:
    async def handler(_command: commands.Command) -> str:
        return 'result'

    bus = MessageBus(
        uow=FakeUnitOfWork(),
        event_handlers={},
        command_handlers={_PingCommand: handler},
    )

    assert await bus.handle(_PingCommand()) == 'result'


async def test_invalid_message_type_is_rejected() -> None:
    bus = MessageBus(FakeUnitOfWork(), event_handlers={}, command_handlers={})

    with pytest.raises(TypeError, match='was not an Event or a Command'):
        await bus.handle(cast('Message', object()))
