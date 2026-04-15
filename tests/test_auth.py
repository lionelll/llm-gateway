import pytest


@pytest.mark.asyncio
async def test_chat_requires_authorization(async_client):
    response = await async_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 401
