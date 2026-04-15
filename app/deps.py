from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.api_key import APIKey
from app.models.user import User
from app.services.auth_service import authenticate_api_key


@dataclass(slots=True)
class AuthContext:
    user: User
    api_key: APIKey
    token: str


async def require_api_key(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> AuthContext:
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
        )

    api_key, user, token = await authenticate_api_key(session, authorization)
    return AuthContext(user=user, api_key=api_key, token=token)


async def require_admin_api_key(
    auth: AuthContext = Depends(require_api_key),
) -> AuthContext:
    if not auth.user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges are required.",
        )
    return auth


async def require_jwt_user(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """Validate a JWT Bearer token and return the corresponding User."""
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header.")

    token = authorization.split(" ", 1)[1].strip()
    from app.services.user_service import decode_access_token

    claims = decode_access_token(token)
    user_id: str = claims.get("sub", "")
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive.")
    return user


async def require_jwt_admin(
    user: User = Depends(require_jwt_user),
) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required.")
    return user


async def require_user_flex(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """Accept either a JWT token (frontend) or a Gateway API Key (curl/SDK)."""
    authorization = request.headers.get("Authorization", "")
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header.")

    token = authorization.split(" ", 1)[-1].strip()

    # Try JWT first (they start with "ey" — base64-encoded JSON header)
    if token.startswith("ey"):
        try:
            from app.services.user_service import decode_access_token
            claims = decode_access_token(token)
            user = (await session.execute(select(User).where(User.id == claims.get("sub", "")))).scalar_one_or_none()
            if user and user.is_active:
                return user
        except Exception:
            pass

    # Fall back to Gateway API Key
    from app.services.auth_service import authenticate_api_key
    _, user, _ = await authenticate_api_key(session, authorization)
    return user
