from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.base import utcnow
from app.models.provider import Provider
from app.models.provider_health import ProviderHealth


async def ensure_provider_health(session: AsyncSession, provider: Provider) -> ProviderHealth:
    stmt = select(ProviderHealth).where(ProviderHealth.provider_id == provider.id)
    health = (await session.execute(stmt)).scalar_one_or_none()
    if health is None:
        health = ProviderHealth(provider_id=provider.id)
        session.add(health)
        await session.flush()
    return health


def provider_available(health: ProviderHealth | None) -> bool:
    if health is None or health.circuit_opened_until is None:
        return True
    return health.circuit_opened_until <= utcnow()


async def mark_provider_success(session: AsyncSession, provider: Provider) -> None:
    health = await ensure_provider_health(session, provider)
    health.consecutive_failures = 0
    health.last_status = "healthy"
    health.circuit_opened_until = None
    health.last_error_message = None


async def mark_provider_failure(session: AsyncSession, provider: Provider, error_message: str) -> None:
    settings = get_settings()
    health = await ensure_provider_health(session, provider)
    health.consecutive_failures += 1
    health.last_failure_at = utcnow()
    health.last_error_message = error_message[:500]

    if health.consecutive_failures >= settings.provider_failure_threshold:
        health.last_status = "cooling_down"
        health.circuit_opened_until = utcnow() + timedelta(seconds=settings.provider_cooldown_seconds)
    else:
        health.last_status = "degraded"
