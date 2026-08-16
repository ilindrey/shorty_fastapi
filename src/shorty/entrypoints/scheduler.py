"""Standalone scheduler for expired-link cleanup."""

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from datetime import UTC

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from shorty.bootstrap import application_runtime
from shorty.config import Settings
from shorty.service_layer.dto import PurgeResult

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

CleanupLinks = Callable[[int], Awaitable[PurgeResult]]


class LinkCleanupScheduler:
    """Runs expired-link cleanup on a fixed interval."""

    def __init__(self, cleanup_links: CleanupLinks, settings: Settings) -> None:
        """Store the application interface and cleanup settings."""
        self._cleanup_links = cleanup_links
        self._settings = settings
        self._scheduler = AsyncIOScheduler(timezone=UTC)

    def start(self) -> None:
        """Register the cleanup job and start the scheduler."""
        self._scheduler.add_job(
            self._run_cleanup,
            trigger='interval',
            minutes=self._settings.cleanup_interval_minutes,
        )
        self._scheduler.start()
        logger.info('Scheduler started.')

    async def _run_cleanup(self) -> None:
        result = await self._cleanup_links(
            self._settings.link_ttl_days,
        )
        logger.info(
            'Cleanup deleted expired links: count=%s, subparts=%s.',
            len(result.deleted_subparts),
            result.deleted_subparts,
        )
        if result.failed_subparts:
            logger.warning(
                'Cleanup could not delete links after concurrency retries: %s',
                result.failed_subparts,
            )

    def shutdown(self) -> None:
        """Stop the scheduler without waiting for the current job to finish."""
        self._scheduler.shutdown(wait=False)


async def serve_scheduler(
    cleanup_links: CleanupLinks,
    settings: Settings,
    stop: Awaitable[object],
) -> None:
    """Run the scheduler until `stop` completes, then shut it down."""
    scheduler = LinkCleanupScheduler(cleanup_links, settings)
    scheduler.start()
    try:
        await stop
    finally:
        scheduler.shutdown()


async def _wait_for_shutdown() -> None:  # pragma: no cover - OS signal integration
    loop = asyncio.get_running_loop()
    stopped = asyncio.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopped.set)
    await stopped.wait()


async def main() -> None:  # pragma: no cover - exercised by the Compose smoke stack
    """Bootstrap infrastructure and serve scheduled cleanup until process shutdown."""
    settings = Settings()
    async with application_runtime(settings) as application:
        await serve_scheduler(
            application.purge_expired_links,
            settings,
            _wait_for_shutdown(),
        )


if __name__ == '__main__':  # pragma: no cover
    asyncio.run(main())
