"""SQLAlchemy repository adapter for the Link aggregate."""

from sqlalchemy.ext.asyncio import AsyncSession

from shorty.domain.model import Link
from shorty.service_layer.ports import AbstractRepository


class SqlAlchemyRepository(AbstractRepository):
    """Repository backed by an async SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind this repository to an active async SQLAlchemy session."""
        super().__init__()
        self.session = session

    async def _add(self, link: Link) -> None:
        self.session.add(link)

    async def _get(self, subpart: str) -> Link | None:
        return await self.session.get(Link, subpart)

    async def delete(self, link: Link) -> None:
        """Remove a Link."""
        await self.session.delete(link)
