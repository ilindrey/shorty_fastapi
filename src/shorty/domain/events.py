"""Domain events raised by the Link aggregate.

Events describe things that already happened to a Link. The Unit of Work
collects them after commit and hands them to the message bus, which fans
each one out to its registered handlers (see service_layer.handlers).
"""

from dataclasses import dataclass


class Event:
    """Marker base class for all domain events."""


@dataclass
class LinkCreated(Event):
    """A new short link was created and needs to be written through to the cache."""

    subpart: str
    url: str


@dataclass
class LinkExpired(Event):
    """A short link passed its retention period and was deleted."""

    subpart: str
