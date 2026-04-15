import pytest
from sqlalchemy import select

from app.models.user import User
from conftest import TestSessionLocal


@pytest.mark.asyncio
async def test_admin_route_requires_admin(async_client, customer_headers):
    response = await async_client.get("/admin/providers", headers=customer_headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_route_accepts_admin_key(async_client, admin_headers):
    response = await async_client.get("/admin/providers", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()[0]["name"] == "test-mock-provider"


@pytest.mark.asyncio
async def test_admin_usage_and_ledger_endpoints(async_client, admin_headers, customer_headers):
    chat_response = await async_client.post(
        "/v1/chat/completions",
        headers=customer_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "report this"}],
        },
    )
    assert chat_response.status_code == 200

    usage_by_user = await async_client.get("/admin/usage/users", headers=admin_headers)
    assert usage_by_user.status_code == 200
    test_user = next(item for item in usage_by_user.json() if item["user_name"] == "test-user")
    assert test_user["request_count"] == 1
    assert test_user["billed_amount"] == "0.01"

    usage_by_model = await async_client.get("/admin/usage/models", headers=admin_headers)
    assert usage_by_model.status_code == 200
    model_row = usage_by_model.json()[0]
    assert model_row["model"] == "gpt-4o-mini"
    assert model_row["request_count"] == 1

    async with TestSessionLocal() as session:
        user = (await session.execute(select(User).where(User.name == "test-user"))).scalar_one()

    ledger_response = await async_client.get(f"/admin/ledger/{user.id}", headers=admin_headers)
    assert ledger_response.status_code == 200
    assert ledger_response.json()[0]["transaction_type"] == "usage_debit"


@pytest.mark.asyncio
async def test_each_created_customer_gets_a_unique_gateway_key(async_client, admin_headers):
    first_response = await async_client.post(
        "/admin/customers",
        headers=admin_headers,
        json={
            "name": "customer-a",
            "payment_amount": "200.00",
            "margin_amount": "40.00",
        },
    )
    second_response = await async_client.post(
        "/admin/customers",
        headers=admin_headers,
        json={
            "name": "customer-b",
            "payment_amount": "200.00",
            "margin_amount": "40.00",
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["api_key"] != second_response.json()["api_key"]
