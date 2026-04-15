import pytest

from app.config import get_settings


@pytest.mark.asyncio
async def test_chat_rate_limit(async_client, customer_headers):
    settings = get_settings()
    original_api_key_limit = settings.api_key_rate_limit_per_minute
    original_ip_limit = settings.ip_rate_limit_per_minute
    settings.api_key_rate_limit_per_minute = 1
    settings.ip_rate_limit_per_minute = 10

    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hello"}],
    }

    first_response = await async_client.post("/v1/chat/completions", headers=customer_headers, json=payload)
    second_response = await async_client.post("/v1/chat/completions", headers=customer_headers, json=payload)

    settings.api_key_rate_limit_per_minute = original_api_key_limit
    settings.ip_rate_limit_per_minute = original_ip_limit

    assert first_response.status_code == 200
    assert second_response.status_code == 429
