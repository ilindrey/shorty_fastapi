"""Service endpoints used by runtime infrastructure."""

from fastapi import APIRouter, status

router = APIRouter(tags=['services'])


@router.get('/health', status_code=status.HTTP_200_OK)
def health() -> dict[str, str]:
    """Report that the application process is ready to serve HTTP requests."""
    return {'status': 'ok'}
