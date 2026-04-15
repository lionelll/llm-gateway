"""
Self-service auth endpoints:
  POST /auth/register  — create account, returns JWT + gateway API key
  POST /auth/login     — email/password login, returns JWT
  GET  /auth/me        — return current user info (JWT required)
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.deps import require_jwt_user
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserMeResponse
from app.services.user_service import create_access_token, login_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    user, _api_key, plain_key = await register_user(
        session,
        name=payload.name,
        email=str(payload.email),
        password=payload.password,
    )
    token = create_access_token(user.id, user.name, user.is_admin)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        name=user.name,
        balance=f"{user.balance:.2f}",
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    user = await login_user(session, email=str(payload.email), password=payload.password)
    token = create_access_token(user.id, user.name, user.is_admin)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        name=user.name,
        balance=f"{user.balance:.2f}",
    )


@router.get("/me", response_model=UserMeResponse)
async def get_me(
    user: User = Depends(require_jwt_user),
) -> UserMeResponse:
    return UserMeResponse(
        user_id=user.id,
        name=user.name,
        email=user.email,
        balance=f"{user.balance:.2f}",
        is_admin=user.is_admin,
    )
