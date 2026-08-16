"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from shorty.bootstrap import application_runtime
from shorty.config import Settings
from shorty.entrypoints.routers import links, services, web
from shorty.exceptions import (
    ConcurrentUpdateError,
    InvalidSubpartError,
    SubpartAlreadyExistsError,
    SubpartGenerationError,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


def _handle_invalid_subpart(_request: Request, exc: Exception) -> JSONResponse:
    error = cast('InvalidSubpartError', exc)
    return JSONResponse(
        {'detail': str(error)},
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


def _handle_duplicate_subpart(_request: Request, exc: Exception) -> JSONResponse:
    error = cast('SubpartAlreadyExistsError', exc)
    return JSONResponse(
        {'detail': f'Subpart {error} is already taken.'},
        status_code=status.HTTP_409_CONFLICT,
    )


def _handle_concurrent_update(
    _request: Request,
    _exc: Exception,
) -> JSONResponse:
    return JSONResponse(
        {'detail': 'The resource was modified concurrently.'},
        status_code=status.HTTP_409_CONFLICT,
    )


def _handle_subpart_generation_failure(
    _request: Request,
    _exc: Exception,
) -> JSONResponse:
    return JSONResponse(
        {'detail': 'Could not generate a short link.'},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception('Unhandled exception while processing request.', exc_info=exc)
    return JSONResponse(
        {'detail': 'Internal server error.'},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(InvalidSubpartError, _handle_invalid_subpart)
    app.add_exception_handler(SubpartAlreadyExistsError, _handle_duplicate_subpart)
    app.add_exception_handler(ConcurrentUpdateError, _handle_concurrent_update)
    app.add_exception_handler(
        SubpartGenerationError,
        _handle_subpart_generation_failure,
    )
    app.add_exception_handler(Exception, _handle_unexpected_error)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    runtime_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Create application dependencies and close them on shutdown."""
        async with application_runtime(runtime_settings) as application:
            app.state.application = application
            logger.info('FastAPI application started.')
            yield

    app = FastAPI(title='Shorty', lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=runtime_settings.session_secret_key,
    )
    _register_exception_handlers(app)

    # Order matters: the catch-all "/{subpart}" must be registered last
    # so it never shadows the API, the UI or FastAPI's own /docs routes.
    app.include_router(services.router)
    app.include_router(links.api_router)
    app.include_router(web.router)
    app.include_router(links.redirect_router)

    return app


app = create_app()
