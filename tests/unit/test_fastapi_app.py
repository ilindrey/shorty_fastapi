"""Unit tests for FastAPI application lifecycle behavior."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from shorty.config import Settings
from shorty.entrypoints import fastapi_app as fastapi_app_module


async def test_lifespan_logs_successful_application_start(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = object()

    @asynccontextmanager
    async def application_runtime(_settings: Settings) -> AsyncIterator[object]:
        yield application

    monkeypatch.setattr(
        fastapi_app_module,
        'application_runtime',
        application_runtime,
    )
    app = fastapi_app_module.create_app(Settings())

    with caplog.at_level(logging.INFO, logger=fastapi_app_module.__name__):
        async with app.router.lifespan_context(app):
            assert app.state.application is application

    assert 'FastAPI application started.' in caplog.messages
