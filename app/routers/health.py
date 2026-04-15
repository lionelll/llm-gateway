from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.redis_client import get_redis_client
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    session: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis_client),
) -> JSONResponse:
    database_status = "ok"
    redis_status = "ok"

    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        database_status = "error"

    try:
        await redis.ping()
    except Exception:
        redis_status = "error"

    overall_status = "ok" if database_status == "ok" and redis_status == "ok" else "degraded"
    status_code = 200 if overall_status == "ok" else 503
    payload = HealthResponse(status=overall_status, database=database_status, redis=redis_status)
    return JSONResponse(status_code=status_code, content=payload.model_dump())
