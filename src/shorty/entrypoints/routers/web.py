"""Jinja-rendered HTTP adapter for the browser UI."""

from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from shorty.entrypoints.routers.deps import get_application, get_owner_session_id
from shorty.entrypoints.routers.schemas import CreateLinkRequest, LinkPageResponse
from shorty.exceptions import InvalidSubpartError, SubpartAlreadyExistsError
from shorty.service_layer.application import ShortyApplication

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[2] / 'templates')


@router.get('/', response_class=HTMLResponse)
async def index(
    request: Request,
    application: Annotated[ShortyApplication, Depends(get_application)],
    owner_session_id: Annotated[str, Depends(get_owner_session_id)],
    page: int = 1,
    error: str | None = None,
) -> HTMLResponse:
    """Render the creation form and the caller's paginated links."""
    result = await application.list_links(owner_session_id, page)
    links = LinkPageResponse.model_validate(result, from_attributes=True)
    return templates.TemplateResponse(
        request,
        'index.html',
        {'links': links, 'error': error, 'host': str(request.base_url)},
    )


@router.post('/links')
async def submit_link(
    application: Annotated[ShortyApplication, Depends(get_application)],
    owner_session_id: Annotated[str, Depends(get_owner_session_id)],
    url: Annotated[str, Form()],
    subpart: Annotated[str, Form()] = '',
) -> RedirectResponse:
    """Validate the form, execute create-link and apply Post/Redirect/Get."""
    try:
        payload = CreateLinkRequest.model_validate(
            {'url': url, 'subpart': subpart or None},
        )
        await application.create_link(
            str(payload.url),
            owner_session_id,
            payload.subpart,
        )
    except SubpartAlreadyExistsError as exc:
        message = f'Subpart {exc} is already taken.'
        return RedirectResponse(f'/?error={quote(message)}', status_code=303)
    except InvalidSubpartError as exc:
        return RedirectResponse(f'/?error={quote(str(exc))}', status_code=303)
    except ValidationError as exc:
        message = exc.errors()[0]['msg']
        return RedirectResponse(f'/?error={quote(message)}', status_code=303)
    return RedirectResponse('/', status_code=303)
