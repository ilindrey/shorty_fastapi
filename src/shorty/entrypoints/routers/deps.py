"""FastAPI dependencies over the application composition root."""

import uuid

from fastapi import Request

from shorty.service_layer.application import ShortyApplication

SESSION_ID_KEY = 'session_id'


def get_application(request: Request) -> ShortyApplication:
    """Provide the framework-independent application interface."""
    return request.app.state.application


def get_owner_session_id(request: Request) -> str:
    """Return the anonymous owner id, creating it on first use."""
    session_id = request.session.get(SESSION_ID_KEY)
    if session_id is None:
        session_id = str(uuid.uuid4())
        request.session[SESSION_ID_KEY] = session_id
    return session_id
