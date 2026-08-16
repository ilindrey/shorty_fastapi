"""End-to-end tests for the link API and public redirects."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from shorty.entrypoints.routers.deps import get_application
from shorty.exceptions import ConcurrentUpdateError, SubpartGenerationError


async def test_create_link_with_explicit_subpart(client: AsyncClient) -> None:
    response = await client.post(
        '/api/links',
        json={'url': 'https://example.com/one', 'subpart': 'mysub'},
    )

    assert response.status_code == 201
    body = response.json()
    assert body == {'subpart': 'mysub', 'url': 'https://example.com/one', 'clicks': 0}


async def test_create_link_generates_subpart_when_omitted(client: AsyncClient) -> None:
    response = await client.post('/api/links', json={'url': 'https://example.com/two'})

    assert response.status_code == 201
    assert response.json()['subpart']


async def test_create_link_rejects_duplicate_subpart(client: AsyncClient) -> None:
    await client.post(
        '/api/links',
        json={'url': 'https://example.com/a', 'subpart': 'dup'},
    )

    response = await client.post(
        '/api/links',
        json={'url': 'https://example.com/b', 'subpart': 'dup'},
    )

    assert response.status_code == 409


async def test_create_link_rejects_invalid_subpart(client: AsyncClient) -> None:
    response = await client.post(
        '/api/links',
        json={'url': 'https://example.com/a', 'subpart': 'api'},
    )

    assert response.status_code == 422


async def test_list_links_is_scoped_and_paginated(client: AsyncClient) -> None:
    for i in range(3):
        await client.post('/api/links', json={'url': f'https://example.com/{i}'})

    response = await client.get('/api/links', params={'page': 1, 'page_size': 2})

    assert response.status_code == 200
    body = response.json()
    assert body['total'] == 3
    assert len(body['items']) == 2
    assert body['page'] == 1
    assert body['page_size'] == 2


async def test_list_links_does_not_leak_across_sessions(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await client.post('/api/links', json={'url': 'https://example.com/mine'})

    other_transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=other_transport,
        base_url='http://test',
    ) as other_client:
        response = await other_client.get('/api/links')

    assert response.json()['total'] == 0


async def test_redirect_follows_shortened_link_and_records_click(
    client: AsyncClient,
) -> None:
    create_response = await client.post(
        '/api/links',
        json={'url': 'https://example.com/target', 'subpart': 'redirme'},
    )
    subpart = create_response.json()['subpart']

    redirect_response = await client.get(f'/{subpart}', follow_redirects=False)

    assert redirect_response.status_code == 307
    assert redirect_response.headers['location'] == 'https://example.com/target'

    # BackgroundTasks run after the response is sent but before the ASGI
    # call returns control to httpx, so the click is already recorded.
    list_response = await client.get('/api/links')
    item = next(i for i in list_response.json()['items'] if i['subpart'] == subpart)
    assert item['clicks'] == 1


async def test_redirect_unknown_subpart_returns_404(client: AsyncClient) -> None:
    response = await client.get('/unknown-subpart', follow_redirects=False)

    assert response.status_code == 404


@pytest.mark.parametrize(
    ('error', 'expected_status', 'expected_detail'),
    [
        (
            ConcurrentUpdateError(),
            409,
            'The resource was modified concurrently.',
        ),
        (
            SubpartGenerationError(),
            503,
            'Could not generate a short link.',
        ),
    ],
)
async def test_application_errors_are_translated_to_http(
    app: FastAPI,
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    def fail() -> None:
        raise error

    app.dependency_overrides[get_application] = fail
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.get('/api/links')
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == expected_status
    assert response.json() == {'detail': expected_detail}


async def test_unexpected_errors_are_hidden(app: FastAPI) -> None:
    def fail() -> None:
        raise RuntimeError('sensitive detail')

    app.dependency_overrides[get_application] = fail
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.get('/trigger-failure')
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {'detail': 'Internal server error.'}
    assert 'sensitive detail' not in response.text
