from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.api_key import APIKey
from app.models.user import User
from app.utils.security import hash_api_key


def extract_bearer_token(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header.",
        )
    return token.strip()


async def authenticate_api_key(session: AsyncSession, authorization: str) -> tuple[APIKey, User, str]:
    settings = get_settings()
    token = extract_bearer_token(authorization)
    key_hash = hash_api_key(token, settings.gateway_api_key_hash_secret)

    stmt = (
        select(APIKey)
        .options(selectinload(APIKey.user))
        .where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True))
    )
    api_key = (await session.execute(stmt)).scalar_one_or_none()

    if api_key is None or api_key.user is None or not api_key.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    return api_key, api_key.user, token


def mark_api_key_used(api_key: APIKey) -> None:
    from app.models.base import utcnow

    api_key.last_used_at = utcnow()
