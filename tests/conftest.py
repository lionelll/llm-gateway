from collections.abc import AsyncIterator
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db import Base
from app.main import app
from app.models.api_key import APIKey
from app.models.model_pricing import ModelPricing
from app.models.provider import Provider
from app.models.provider_health import ProviderHealth
from app.models.user import User
from app.redis_client import get_redis_client
from app.utils.security import hash_api_key


class FakeRedis:
    def __init__(self) -> None:
        self.storage: dict[str, int] = {}

    async def ping(self) -> bool:
        return True

    async def incr(self, key: str) -> int:
        self.storage[key] = self.storage.get(key, 0) + 1
        return self.storage[key]

    async def expire(self, key: str, _: int) -> bool:
        return key in self.storage


TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_gateway.db"
test_engine = create_async_engine(TEST_DATABASE_URL, future=True)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)


async def override_session() -> AsyncIterator[AsyncSession]:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def prepare_app() -> AsyncIterator[None]:
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    settings = get_settings()
    admin_key_hash = hash_api_key("test-admin-key", settings.gateway_api_key_hash_secret)
    hashed_key = hash_api_key("test-gateway-key", settings.gateway_api_key_hash_secret)

    async with TestSessionLocal() as session:
        admin_user = User(name="test-admin", is_admin=True, balance=Decimal("0.00"))
        customer = User(name="test-user", balance=Decimal("50.00"))
        session.add_all([admin_user, customer])
        await session.flush()

        admin_api_key = APIKey(
            user_id=admin_user.id,
            key_hash=admin_key_hash,
            key_prefix="test-admin",
            description="admin key",
        )
        api_key = APIKey(
            user_id=customer.id,
            key_hash=hashed_key,
            key_prefix="test-gateway",
            description="customer key",
        )
        provider = Provider(
            name="test-mock-provider",
            provider_type="mock",
            base_url="mock://local",
            api_key=None,
            supported_models=["gpt-4o-mini"],
            priority=100,
            weight=100,
            is_active=True,
            timeout_seconds=5,
        )
        pricing = ModelPricing(
            provider_id=provider.id,
            model_name="gpt-4o-mini",
            input_cost_per_1k_tokens=Decimal("0.100000"),
            output_cost_per_1k_tokens=Decimal("0.200000"),
            currency="CNY",
            is_active=True,
        )
        session.add_all([admin_api_key, api_key, provider])
        await session.flush()
        session.add(ProviderHealth(provider_id=provider.id))
        pricing.provider_id = provider.id
        session.add(pricing)
        await session.commit()

    fake_redis = FakeRedis()

    async def override_redis() -> AsyncIterator[FakeRedis]:
        yield fake_redis

    app.dependency_overrides.clear()
    app.dependency_overrides[get_redis_client] = override_redis
    from app.db import get_async_session

    app.dependency_overrides[get_async_session] = override_session

    yield

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def customer_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-gateway-key"}


@pytest_asyncio.fixture
async def admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-admin-key"}
