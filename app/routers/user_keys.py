"""
Self-service API Key management for authenticated users (JWT auth).
  GET    /v1/me/keys          — list own keys
  POST   /v1/me/keys          — create a new key
  DELETE /v1/me/keys/{key_id} — revoke a key
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_async_session
from app.deps import require_jwt_user
from app.models.api_key import APIKey
from app.models.user import User
from app.utils.security import generate_api_key, hash_api_key

router = APIRouter(prefix="/v1/me", tags=["user-keys"])


class KeyCreateRequest(BaseModel):
    description: str | None = None


class KeyResponse(BaseModel):
    id: str
    key_prefix: str
    description: str | None
    is_active: bool
    last_used_at: str | None
    created_at: str


class KeyCreateResponse(KeyResponse):
    api_key: str  # only returned once on creation


@router.get("/keys", response_model=list[KeyResponse])
async def list_keys(
    user: User = Depends(require_jwt_user),
    session: AsyncSession = Depends(get_async_session),
):
    keys = list((await session.scalars(
        select(APIKey).where(APIKey.user_id == user.id).order_by(APIKey.created_at.desc())
    )).all())
    return [
        KeyResponse(
            id=k.id,
            key_prefix=k.key_prefix,
            description=k.description,
            is_active=k.is_active,
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
            created_at=k.created_at.isoformat(),
        )
        for k in keys
    ]


@router.post("/keys", response_model=KeyCreateResponse, status_code=201)
async def create_key(
    payload: KeyCreateRequest,
    user: User = Depends(require_jwt_user),
    session: AsyncSession = Depends(get_async_session),
):
    settings = get_settings()
    plain_key = generate_api_key("gw")
    key = APIKey(
        user_id=user.id,
        key_hash=hash_api_key(plain_key, settings.gateway_api_key_hash_secret),
        key_prefix=plain_key[:12],
        description=payload.description,
    )
    session.add(key)
    await session.commit()
    await session.refresh(key)
    return KeyCreateResponse(
        id=key.id,
        key_prefix=key.key_prefix,
        description=key.description,
        is_active=key.is_active,
        last_used_at=None,
        created_at=key.created_at.isoformat(),
        api_key=plain_key,
    )


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: str,
    user: User = Depends(require_jwt_user),
    session: AsyncSession = Depends(get_async_session),
):
    key = (await session.execute(
        select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user.id)
    )).scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found.")
    key.is_active = False
    await session.commit()
