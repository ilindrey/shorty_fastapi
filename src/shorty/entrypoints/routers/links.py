"""HTTP adapters for creating, listing, and resolving shortened links."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from shorty.entrypoints.routers.deps import get_application, get_owner_session_id
from shorty.entrypoints.routers.schemas import (
    CreateLinkRequest,
    LinkPageResponse,
    LinkResponse,
)
from shorty.service_layer.application import ShortyApplication

api_router = APIRouter(prefix='/api', tags=['links'])
redirect_router = APIRouter()


@api_router.post(
    '/links',
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_link(
    payload: CreateLinkRequest,
    application: Annotated[ShortyApplication, Depends(get_application)],
    owner_session_id: Annotated[str, Depends(get_owner_session_id)],
) -> LinkResponse:
    """Shorten a URL, optionally under a caller-chosen subpart."""
    created = await application.create_link(
        str(payload.url),
        owner_session_id,
        payload.subpart,
    )
    return LinkResponse.model_validate(created, from_attributes=True)


@api_router.get('/links', response_model=LinkPageResponse)
async def list_links(
    application: Annotated[ShortyApplication, Depends(get_application)],
    owner_session_id: Annotated[str, Depends(get_owner_session_id)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> LinkPageResponse:
    """List the caller's links, paginated and newest first."""
    result = await application.list_links(owner_session_id, page, page_size)
    return LinkPageResponse.model_validate(result, from_attributes=True)


@redirect_router.get('/{subpart}')
async def redirect_to_url(
    subpart: str,
    background_tasks: BackgroundTasks,
    application: Annotated[ShortyApplication, Depends(get_application)],
) -> RedirectResponse:
    """Resolve a short link and record its click after sending the response."""
    url = await application.resolve_redirect(subpart)
    if url is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Unknown short link.')
    background_tasks.add_task(application.record_click, subpart)
    return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
