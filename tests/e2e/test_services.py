"""End-to-end tests for service endpoints."""

from httpx import AsyncClient


async def test_health_reports_service_is_ready(client: AsyncClient) -> None:
    response = await client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


async def test_health_is_grouped_under_services_in_openapi(
    client: AsyncClient,
) -> None:
    response = await client.get('/openapi.json')

    assert response.json()['paths']['/health']['get']['tags'] == ['services']
