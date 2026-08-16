"""End-to-end tests for the Jinja-rendered UI routes."""

from httpx import AsyncClient


async def test_index_renders_empty_state(client: AsyncClient) -> None:
    response = await client.get('/')

    assert response.status_code == 200
    assert 'No shortened links yet.' in response.text


async def test_index_mints_a_session_cookie_on_first_visit(client: AsyncClient) -> None:
    response = await client.get('/')

    assert 'session' in response.cookies


async def test_submit_link_then_index_lists_it(client: AsyncClient) -> None:
    submit_response = await client.post(
        '/links',
        data={'url': 'https://example.com/via-form', 'subpart': 'formsub'},
        follow_redirects=False,
    )

    assert submit_response.status_code == 303
    assert submit_response.headers['location'] == '/'
    # The session cookie minted by the inner API call must reach the browser.
    assert 'session' in submit_response.cookies

    index_response = await client.get('/')

    assert 'https://example.com/via-form' in index_response.text
    assert 'formsub' in index_response.text


async def test_submit_link_with_duplicate_subpart_redirects_with_error(
    client: AsyncClient,
) -> None:
    await client.post(
        '/links',
        data={'url': 'https://example.com/a', 'subpart': 'clash'},
    )

    submit_response = await client.post(
        '/links',
        data={'url': 'https://example.com/b', 'subpart': 'clash'},
        follow_redirects=False,
    )

    assert submit_response.status_code == 303
    assert submit_response.headers['location'].startswith('/?error=')

    error_page = await client.get(submit_response.headers['location'])
    assert 'already taken' in error_page.text


async def test_submit_link_with_invalid_url_redirects_with_error(
    client: AsyncClient,
) -> None:
    response = await client.post(
        '/links',
        data={'url': 'not-a-url', 'subpart': 'invalidurl'},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers['location'].startswith('/?error=')


async def test_submit_link_with_reserved_subpart_redirects_with_error(
    client: AsyncClient,
) -> None:
    response = await client.post(
        '/links',
        data={'url': 'https://example.com', 'subpart': 'api'},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers['location'].startswith('/?error=')
