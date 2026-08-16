"""Commands accepted by the message bus.

Unlike events, a command targets exactly one handler and is expected to
either succeed or raise - callers may want to react to the failure.
"""

from dataclasses import dataclass


class Command:
    """Marker base class for all commands."""


@dataclass
class CreateLink(Command):
    """Shorten `url`, optionally under a caller-chosen `subpart`."""

    url: str
    owner_session_id: str
    subpart: str | None = None


@dataclass
class RecordClick(Command):
    """Register that `subpart` was just followed by a visitor."""

    subpart: str


@dataclass
class ExpireLink(Command):
    """Delete one expired link by subpart."""

    subpart: str
