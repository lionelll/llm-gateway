from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.api_key import APIKey
from app.models.user import User
from conftest import TestSessionLocal


@pytest.mark.asyncio
async def test_balance_endpoint_and_deduction(async_client, customer_headers):
    starting_balance_response = await async_client.get("/v1/me/balance", headers=customer_headers)
    assert starting_balance_response.status_code == 200
    assert starting_balance_response.json()["balance"] == "50.00"

    response = await async_client.post(
        "/v1/chat/completions",
        headers=customer_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "bill me"}],
        },
    )
    assert response.status_code == 200
    assert response.headers["X-Balance-Remaining"] == "49.99"

    ending_balance_response = await async_client.get("/v1/me/balance", headers=customer_headers)
    assert ending_balance_response.status_code == 200
    assert ending_balance_response.json()["balance"] == "49.99"


@pytest.mark.asyncio
async def test_insufficient_balance_returns_402(async_client, customer_headers):
    async with TestSessionLocal() as session:
        user = (await session.execute(select(User).where(User.name == "test-user"))).scalar_one()
        user.balance = Decimal("0.00")
        await session.commit()

    response = await async_client.post(
        "/v1/chat/completions",
        headers=customer_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "no funds"}],
            "max_tokens": 32,
        },
    )

    assert response.status_code == 402


@pytest.mark.asyncio
async def test_zero_balance_disables_key_and_topup_reactivates(async_client, admin_headers, customer_headers):
    # Simulate zero-balance state: balance=0, key disabled with reason
    async with TestSessionLocal() as session:
        user = (await session.execute(select(User).where(User.name == "test-user"))).scalar_one()
        user_id = user.id
        user.balance = Decimal("0.00")
        api_key = (await session.execute(
            select(APIKey).where(APIKey.key_prefix == "test-gateway")
        )).scalar_one()
        api_key.is_active = False
        api_key.disabled_reason = "zero_balance"
        await session.commit()

    # Disabled key should be rejected
    blocked_response = await async_client.post(
        "/v1/chat/completions",
        headers=customer_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "should be blocked"}],
        },
    )
    assert blocked_response.status_code == 401

    # Topup should reactivate the key
    topup_response = await async_client.post(
        "/admin/topups",
        headers=admin_headers,
        json={
            "user_id": user_id,
            "idempotency_key": "test-reactivate-001",
            "payment_amount": "10.00",
            "granted_balance": "8.00",
            "margin_amount": "2.00",
            "note": "reactivate customer",
        },
    )
    assert topup_response.status_code == 200
    assert topup_response.json()["balance"] == "8.00"

    async with TestSessionLocal() as session:
        api_key = (await session.execute(select(APIKey).where(APIKey.key_prefix == "test-gateway"))).scalar_one()
        assert api_key.is_active is True
        assert api_key.disabled_reason is None

    # Reactivated key should work
    resumed_response = await async_client.post(
        "/v1/chat/completions",
        headers=customer_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "back again"}],
        },
    )
    assert resumed_response.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_endpoint_returns_recent_activity(async_client, customer_headers):
    response = await async_client.post(
        "/v1/chat/completions",
        headers=customer_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "show me the dashboard"}],
        },
    )
    assert response.status_code == 200

    dashboard_response = await async_client.get("/v1/me/dashboard?limit=5", headers=customer_headers)
    assert dashboard_response.status_code == 200

    payload = dashboard_response.json()
    assert payload["user_name"] == "test-user"
    assert payload["is_admin"] is False
    assert payload["usage_summary"]["request_count"] == 1
    assert payload["usage_summary"]["total_tokens"] > 0
    assert payload["recent_requests"][0]["model"] == "gpt-4o-mini"
    assert payload["recent_ledger"][0]["transaction_type"] == "usage_debit"
    assert payload["model_usage"][0]["provider_type"] == "mock"
