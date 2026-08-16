"""SQLAlchemy Unit of Work adapter."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from shorty.adapters.repository import SqlAlchemyRepository
from shorty.exceptions import ConcurrentUpdateError, SubpartAlreadyExistsError
from shorty.service_layer.ports import AbstractUnitOfWork

_UNIQUE_VIOLATION_SQLSTATE = '23505'
_LINK_PRIMARY_KEY_CONSTRAINT = 'links_pkey'


def _is_link_primary_key_violation(exc: IntegrityError) -> bool:
    current: BaseException | None = exc.orig
    while current is not None:
        if (
            getattr(current, 'sqlstate', None) == _UNIQUE_VIOLATION_SQLSTATE
            and getattr(current, 'constraint_name', None)
            == _LINK_PRIMARY_KEY_CONSTRAINT
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """Open one SQLAlchemy session and transaction per use case."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Store the factory used to create a fresh session."""
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        """Open a session and its repository."""
        self._session = self._session_factory()
        self.links = SqlAlchemyRepository(self._session)
        return await super().__aenter__()  # type: ignore[return-value]

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Roll back pending work and close the session."""
        await super().__aexit__(exc_type, exc_value, traceback)
        await self._require_session().close()

    async def commit(self) -> None:
        """Commit, translating ORM concurrency errors into the application port."""
        try:
            await self._require_session().commit()
        except StaleDataError as exc:
            raise ConcurrentUpdateError('Aggregate version is stale.') from exc
        except IntegrityError as exc:
            if not _is_link_primary_key_violation(exc):
                raise
            subpart = next(iter(self.links.seen)).subpart
            raise SubpartAlreadyExistsError(subpart) from exc

    async def rollback(self) -> None:
        """Roll back pending changes."""
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError('SqlAlchemyUnitOfWork used outside "async with uow".')
        return self._session
