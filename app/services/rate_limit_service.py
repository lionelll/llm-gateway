from datetime import datetime, timezone

from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.config import get_settings


def build_rate_limit_bucket(prefix: str, identifier: str) -> str:
    current_minute = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    return f"ratelimit:{prefix}:{identifier}:{current_minute}"


async def _enforce_single_limit(redis: Redis, prefix: str, identifier: str, limit: int, detail: str) -> None:
    key = build_rate_limit_bucket(prefix, identifier)
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if count > limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)


async def enforce_rate_limits(redis: Redis, api_key_id: str, client_ip: str) -> None:
    settings = get_settings()
    await _enforce_single_limit(
        redis=redis,
        prefix="api_key",
        identifier=api_key_id,
        limit=settings.api_key_rate_limit_per_minute,
        detail="API key rate limit exceeded.",
    )
    await _enforce_single_limit(
        redis=redis,
        prefix="ip",
        identifier=client_ip,
        limit=settings.ip_rate_limit_per_minute,
        detail="IP rate limit exceeded.",
    )
