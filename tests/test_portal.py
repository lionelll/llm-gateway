import pytest


@pytest.mark.asyncio
async def test_portal_page_serves_html(async_client):
    response = await async_client.get("/portal")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "LLM Gateway Portal" in response.text


@pytest.mark.asyncio
async def test_portal_assets_are_served(async_client):
    css_response = await async_client.get("/assets/portal.css")
    js_response = await async_client.get("/assets/portal.js")

    assert css_response.status_code == 200
    assert "text/css" in css_response.headers["content-type"]
    assert js_response.status_code == 200
    assert "javascript" in js_response.headers["content-type"]


@pytest.mark.asyncio
async def test_portal_login_accepts_matching_username_and_key(async_client):
    response = await async_client.post(
        "/v1/portal/login",
        json={
            "user_name": "test-user",
            "api_key": "test-gateway-key",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_name"] == "test-user"
    assert payload["is_admin"] is False


@pytest.mark.asyncio
async def test_portal_login_rejects_username_key_mismatch(async_client):
    response = await async_client.post(
        "/v1/portal/login",
        json={
            "user_name": "wrong-user",
            "api_key": "test-gateway-key",
        },
    )

    assert response.status_code == 401
