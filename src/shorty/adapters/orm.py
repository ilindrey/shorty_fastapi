"""SQLAlchemy table and imperative mapping for the domain model.

`domain.model.Link` remains a plain dataclass with no SQLAlchemy imports. The
ORM depends on the domain model, not the other way around.
"""

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table
from sqlalchemy import event as sa_event
from sqlalchemy.orm import class_mapper, registry
from sqlalchemy.orm.exc import UnmappedClassError

from shorty.domain.model import Link

metadata = MetaData()
mapper_registry = registry(metadata=metadata)

links_table = Table(
    'links',
    metadata,
    Column('subpart', String(32), primary_key=True),
    Column('url', String(2048), nullable=False),
    Column('owner_session_id', String(36), nullable=False, index=True),
    Column('created_at', DateTime(timezone=True), nullable=False, index=True),
    Column('clicks', Integer, nullable=False, default=0),
    Column('version_number', Integer, nullable=False, default=0),
)


def start_mappers() -> None:
    """Map `Link` onto `links_table`.

    Calling this function more than once in the same process is safe.
    """
    try:
        class_mapper(Link)
    except UnmappedClassError:
        pass
    else:
        return

    mapper_registry.map_imperatively(
        Link,
        links_table,
        version_id_col=links_table.c.version_number,
        version_id_generator=False,
    )

    @sa_event.listens_for(Link, 'load')
    def _reset_events_on_load(link: Link, _context: object) -> None:
        """Initialize the event list when SQLAlchemy loads a Link.

        `Link.events` is not mapped, and SQLAlchemy bypasses `__init__` when it
        creates an instance from a row.
        """
        link.events = []
