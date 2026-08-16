"""Unit tests for the scheduled cleanup adapter."""

import asyncio
import logging

import pytest

from shorty.config import Settings
from shorty.entrypoints import scheduler as scheduler_module
from shorty.entrypoints.scheduler import LinkCleanupScheduler, serve_scheduler
from shorty.service_layer.dto import PurgeResult


class FakeCleanup:
    """Callable cleanup fake with a call log."""

    def __init__(self, result: PurgeResult | None = None) -> None:
        """Start with no cleanup calls."""
        self.cleanup_days: list[int] = []
        self.result = result or PurgeResult(('one', 'two', 'three'), ())

    async def __call__(self, older_than_days: int) -> PurgeResult:
        """Record and report a deterministic purge result."""
        self.cleanup_days.append(older_than_days)
        return self.result


async def test_cleanup_dispatches_purge_command_with_configured_ttl() -> None:
    cleanup = FakeCleanup()
    scheduler = LinkCleanupScheduler(cleanup, Settings(link_ttl_days=21))

    await scheduler._run_cleanup()

    assert cleanup.cleanup_days == [21]


async def test_cleanup_reports_identifiers_left_after_retries() -> None:
    cleanup = FakeCleanup(PurgeResult((), ('failed',)))
    scheduler = LinkCleanupScheduler(cleanup, Settings())

    await scheduler._run_cleanup()

    assert cleanup.cleanup_days == [14]


async def test_cleanup_job_is_scheduled_for_a_future_run(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cleanup = FakeCleanup()
    scheduler = LinkCleanupScheduler(
        cleanup,
        Settings(cleanup_interval_minutes=60),
    )

    with caplog.at_level(logging.INFO, logger=scheduler_module.__name__):
        scheduler.start()
    try:
        jobs = scheduler._scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].next_run_time is not None
        assert 'Scheduler started.' in caplog.messages
    finally:
        scheduler.shutdown()


async def test_serve_scheduler_stops_cleanly() -> None:
    cleanup = FakeCleanup()

    await serve_scheduler(cleanup, Settings(), asyncio.sleep(0))
