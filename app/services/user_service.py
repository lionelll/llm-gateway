"""
User registration and JWT authentication service.
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.api_key import APIKey
from app.models.user import User
from app.utils.security import generate_api_key, hash_api_key

logger = logging.getLogger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, name: str, is_admin: bool) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": user_id,
        "name": name,
        "is_admin": is_admin,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        ) from exc


async def register_user(
    session: AsyncSession,
    *,
    name: str,
    email: str,
    password: str,
) -> tuple[User, APIKey, str]:
    """
    Create a new user with email/password and issue a gateway API key.
    Returns (user, api_key, plain_key).
    """
    settings = get_settings()

    # Uniqueness checks
    existing_name = (await session.execute(select(User).where(User.name == name))).scalar_one_or_none()
    if existing_name:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken.")

    existing_email = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing_email:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        is_admin=False,
        is_active=True,
    )
    session.add(user)
    await session.flush()

    plain_key = generate_api_key("gw")
    api_key = APIKey(
        user_id=user.id,
        key_hash=hash_api_key(plain_key, settings.gateway_api_key_hash_secret),
        key_prefix=plain_key[:12],
        description="Default key",
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(user)
    return user, api_key, plain_key


async def login_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> User:
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None or not user.password_hash or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled.")
    return user
