"""SQLAlchemy CQRS read-model adapter."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shorty.adapters.orm import links_table
from shorty.service_layer.dto import LinkSummary, RedirectTarget
from shorty.service_layer.ports import AbstractLinkReadModel


class SqlAlchemyLinkReadModel(AbstractLinkReadModel):
    """Execute optimized read-only queries without building aggregates."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Store the factory used for short-lived read sessions."""
        self._session_factory = session_factory

    async def get_redirect_target(self, subpart: str) -> RedirectTarget | None:
        """Return redirect data for `subpart`."""
        async with self._session_factory() as session:
            stmt = select(links_table.c.url, links_table.c.created_at).where(
                links_table.c.subpart == subpart,
            )
            row = (await session.execute(stmt)).one_or_none()
        return RedirectTarget(row.url, row.created_at) if row is not None else None

    async def list_links(
        self,
        owner_session_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[LinkSummary], int]:
        """Return an owner-scoped page ordered newest first."""
        owned_by = links_table.c.owner_session_id == owner_session_id
        async with self._session_factory() as session:
            total = (
                await session.execute(
                    select(func.count()).select_from(links_table).where(owned_by),
                )
            ).scalar_one()
            rows = (
                await session.execute(
                    select(
                        links_table.c.subpart,
                        links_table.c.url,
                        links_table.c.clicks,
                    )
                    .where(owned_by)
                    .order_by(links_table.c.created_at.desc())
                    .limit(page_size)
                    .offset((page - 1) * page_size),
                )
            ).all()
        return [LinkSummary(r.subpart, r.url, r.clicks) for r in rows], total

    async def list_expired_subparts(
        self,
        cutoff: datetime,
        after: str | None,
        limit: int,
    ) -> list[str]:
        """Return expired subparts using stable keyset pagination."""
        conditions = [links_table.c.created_at < cutoff]
        if after is not None:
            conditions.append(links_table.c.subpart > after)
        stmt = (
            select(links_table.c.subpart)
            .where(*conditions)
            .order_by(links_table.c.subpart)
            .limit(limit)
        )
        async with self._session_factory() as session:
            return list((await session.execute(stmt)).scalars().all())
