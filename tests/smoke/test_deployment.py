"""Network-level checks against the production image in the test stack."""

import os

from httpx import AsyncClient


async def test_deployed_health_is_reachable() -> None:
    """Check the production image through its real network interface."""
    async with AsyncClient(base_url=os.environ['DEPLOYED_API_URL']) as client:
        response = await client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


async def test_deployed_index_is_reachable_after_database_tests() -> None:
    """Check that test cleanup preserves the migrated schema."""
    async with AsyncClient(base_url=os.environ['DEPLOYED_API_URL']) as client:
        response = await client.get('/')

    assert response.status_code == 200
    assert 'No shortened links yet.' in response.text
