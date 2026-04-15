from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.deps import AuthContext, require_api_key, require_user_flex
from app.models.user import User
from app.schemas.billing import BalanceResponse, DashboardResponse, PortalLoginRequest
from app.services.auth_service import authenticate_api_key
from app.services.reporting_service import get_user_dashboard

router = APIRouter(tags=["billing"])


@router.get("/v1/me/balance", response_model=BalanceResponse)
async def get_my_balance(
    user: User = Depends(require_user_flex),
) -> BalanceResponse:
    return BalanceResponse(
        user_id=user.id,
        user_name=user.name,
        balance=user.balance,
        key_prefix="",
    )


@router.get("/v1/me/dashboard", response_model=DashboardResponse)
async def get_my_dashboard(
    user: User = Depends(require_user_flex),
    session: AsyncSession = Depends(get_async_session),
    limit: int = Query(default=12, ge=1, le=50),
) -> DashboardResponse:
    return await get_user_dashboard(
        session,
        user=user,
        key_prefix="",
        recent_limit=limit,
    )


@router.post("/v1/portal/login", response_model=DashboardResponse)
async def portal_login(
    payload: PortalLoginRequest,
    session: AsyncSession = Depends(get_async_session),
) -> DashboardResponse:
    api_key, user, _ = await authenticate_api_key(session, f"Bearer {payload.api_key}")
    if user.name != payload.user_name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User name and API key do not match.",
        )

    return await get_user_dashboard(
        session,
        user=user,
        key_prefix=api_key.key_prefix,
        recent_limit=12,
    )
