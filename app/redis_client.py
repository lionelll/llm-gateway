from collections.abc import AsyncIterator

from redis.asyncio import Redis

from app.config import get_settings

settings = get_settings()
redis_client: Redis | None = None


async def init_redis_client() -> Redis:
    global redis_client

    if redis_client is None:
        redis_client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    return redis_client


async def close_redis_client() -> None:
    global redis_client

    if redis_client is not None:
        await redis_client.close()
        redis_client = None


async def get_redis_client() -> AsyncIterator[Redis]:
    client = await init_redis_client()
    yield client
