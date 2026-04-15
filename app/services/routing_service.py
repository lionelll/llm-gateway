from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.provider import Provider
from app.services.provider_health_service import provider_available


def provider_supports_model(provider: Provider, model: str) -> bool:
    return model in provider.supported_models or "*" in provider.supported_models


async def get_provider_candidates(session: AsyncSession, model: str) -> list[Provider]:
    stmt = (
        select(Provider)
        .options(selectinload(Provider.health))
        .where(Provider.is_active.is_(True))
        .order_by(Provider.priority.desc(), Provider.weight.desc(), Provider.name.asc())
    )
    providers = list((await session.scalars(stmt)).all())
    return [
        provider
        for provider in providers
        if provider_supports_model(provider, model) and provider_available(provider.health)
    ]
