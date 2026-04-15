import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.config import get_settings
from app.db import AsyncSessionLocal
from app.models.api_key import APIKey
from app.models.balance_transaction import BalanceTransaction
from app.models.model_pricing import ModelPricing
from app.models.provider import Provider
from app.models.provider_health import ProviderHealth
from app.models.user import User
from app.services.billing_service import apply_topup
from app.utils.security import hash_api_key


def unique_items(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


async def seed_user_and_api_key() -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        admin_user = (await session.execute(select(User).where(User.name == "admin-user"))).scalar_one_or_none()
        if admin_user is None:
            admin_user = User(name="admin-user", is_admin=True, balance=Decimal("0.00"))
            session.add(admin_user)
            await session.flush()

        admin_key_hash = hash_api_key(settings.seed_admin_api_key, settings.gateway_api_key_hash_secret)
        admin_key = (await session.execute(select(APIKey).where(APIKey.key_hash == admin_key_hash))).scalar_one_or_none()
        if admin_key is None:
            session.add(
                APIKey(
                    user_id=admin_user.id,
                    key_hash=admin_key_hash,
                    key_prefix=settings.seed_admin_api_key[:12],
                    description="Bootstrap admin key",
                )
            )

        customer = (await session.execute(select(User).where(User.name == "demo-user"))).scalar_one_or_none()
        if customer is None:
            customer = User(name="demo-user", is_admin=False, balance=Decimal("0.00"))
            session.add(customer)
            await session.flush()

        gateway_key = settings.seed_gateway_api_key
        gateway_key_hash = hash_api_key(gateway_key, settings.gateway_api_key_hash_secret)
        api_key = (await session.execute(select(APIKey).where(APIKey.key_hash == gateway_key_hash))).scalar_one_or_none()
        if api_key is None:
            api_key = APIKey(
                user_id=customer.id,
                key_hash=gateway_key_hash,
                key_prefix=gateway_key[:12],
                description="Bootstrap demo customer key",
            )
            session.add(api_key)
            await session.flush()

        if settings.enable_mock_provider:
            mock_provider = (
                await session.execute(select(Provider).where(Provider.name == "local-mock-provider"))
            ).scalar_one_or_none()
            if mock_provider is None:
                mock_provider = Provider(
                    name="local-mock-provider",
                    provider_type="mock",
                    base_url="mock://local",
                    api_key=None,
                    supported_models=unique_items(
                        [settings.default_mock_model, "gpt-4o-mini", "gpt-3.5-turbo"]
                    ),
                    priority=100,
                    weight=100,
                    is_active=True,
                    timeout_seconds=5,
                )
                session.add(mock_provider)
                await session.flush()
            mock_provider_health = (
                await session.execute(select(ProviderHealth).where(ProviderHealth.provider_id == mock_provider.id))
            ).scalar_one_or_none()
            if mock_provider_health is None:
                session.add(ProviderHealth(provider_id=mock_provider.id))
            await upsert_pricing(
                session,
                provider=mock_provider,
                model_name="gpt-4o-mini",
                input_cost=Decimal("0.100000"),
                output_cost=Decimal("0.200000"),
            )
            await upsert_pricing(
                session,
                provider=mock_provider,
                model_name="gpt-3.5-turbo",
                input_cost=Decimal("0.080000"),
                output_cost=Decimal("0.160000"),
            )

        if settings.seed_provider_base_url and settings.seed_provider_api_key:
            provider_name = settings.seed_provider_name or "seed-provider"
            provider = (
                await session.execute(select(Provider).where(Provider.name == provider_name))
            ).scalar_one_or_none()
            if provider is None:
                provider = Provider(
                    name=provider_name,
                    provider_type=settings.seed_provider_type,
                    base_url=settings.seed_provider_base_url,
                    api_key=settings.seed_provider_api_key,
                    supported_models=unique_items(
                        settings.seed_provider_models or [settings.default_mock_model]
                    ),
                    priority=settings.seed_provider_priority,
                    weight=settings.seed_provider_weight,
                    is_active=True,
                    timeout_seconds=settings.seed_provider_timeout_seconds,
                )
                session.add(provider)
                await session.flush()
            provider_health = (
                await session.execute(select(ProviderHealth).where(ProviderHealth.provider_id == provider.id))
            ).scalar_one_or_none()
            if provider_health is None:
                session.add(ProviderHealth(provider_id=provider.id))

        initial_topup = (
            await session.execute(
                select(BalanceTransaction).where(
                    BalanceTransaction.user_id == customer.id,
                    BalanceTransaction.transaction_type == "topup",
                    BalanceTransaction.note == "Seed demo initial balance",
                )
            )
        ).scalar_one_or_none()
        if initial_topup is None:
            session.add(
                apply_topup(
                    user=customer,
                    payment_amount=settings.seed_demo_payment_amount,
                    granted_balance=settings.seed_demo_credited_amount,
                    margin_amount=settings.seed_demo_margin_amount,
                    note="Seed demo initial balance",
                    api_key_id=api_key.id,
                )
            )

        await session.commit()

    print("Seed data initialized successfully.")
    print(f"Customer credited balance: {settings.seed_demo_credited_amount}")
    if settings.enable_mock_provider:
        print(f"Mock provider enabled for model(s): {settings.default_mock_model}, gpt-3.5-turbo")
    # Note: API keys are NOT printed to avoid leaking secrets in logs.


async def upsert_pricing(
    session,
    *,
    provider: Provider,
    model_name: str,
    input_cost: Decimal,
    output_cost: Decimal,
) -> None:
    pricing = (
        await session.execute(
            select(ModelPricing).where(
                ModelPricing.provider_id == provider.id,
                ModelPricing.model_name == model_name,
            )
        )
    ).scalar_one_or_none()
    if pricing is None:
        pricing = ModelPricing(
            provider_id=provider.id,
            model_name=model_name,
        )
        session.add(pricing)
    pricing.input_cost_per_1k_tokens = input_cost
    pricing.output_cost_per_1k_tokens = output_cost
    pricing.currency = "CNY"
    pricing.is_active = True


def main() -> None:
    asyncio.run(seed_user_and_api_key())


if __name__ == "__main__":
    main()
