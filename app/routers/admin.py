from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import get_async_session
from app.deps import AuthContext, require_admin_api_key
from app.models.api_key import APIKey
from app.models.balance_transaction import BalanceTransaction
from app.models.model_pricing import ModelPricing
from app.models.provider import Provider
from app.models.provider_health import ProviderHealth
from app.models.user import User
from app.schemas.admin import (
    AdminBalanceResponse,
    AdminModelUsageResponse,
    AdminUserUsageResponse,
    CustomerCreateRequest,
    CustomerCreateResponse,
    LedgerEntryResponse,
    ModelPricingUpsertRequest,
    ProviderCreateRequest,
    TopUpRequest,
)
from app.schemas.provider import ProviderRead
from app.services.billing_service import apply_topup, reactivate_user_api_keys, resolve_topup_amounts
from app.services.reporting_service import get_model_usage_report, get_user_ledger, get_user_usage_report
from app.utils.security import generate_api_key, hash_api_key

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


@router.get("/providers", response_model=list[ProviderRead])
async def list_providers(
    _: AuthContext = Depends(require_admin_api_key),
    session: AsyncSession = Depends(get_async_session),
) -> list[ProviderRead]:
    stmt = (
        select(Provider)
        .options(selectinload(Provider.health))
        .order_by(Provider.priority.desc(), Provider.weight.desc(), Provider.name.asc())
    )
    providers = list((await session.scalars(stmt)).all())

    return [
        ProviderRead(
            id=provider.id,
            name=provider.name,
            provider_type=provider.provider_type,
            base_url=provider.base_url,
            supported_models=provider.supported_models,
            priority=provider.priority,
            weight=provider.weight,
            is_active=provider.is_active,
            timeout_seconds=provider.timeout_seconds,
            health_status=provider.health.last_status if provider.health else "healthy",
            consecutive_failures=provider.health.consecutive_failures if provider.health else 0,
            circuit_opened_until=provider.health.circuit_opened_until if provider.health else None,
        )
        for provider in providers
    ]


@router.post("/providers", response_model=ProviderRead)
async def create_provider(
    payload: ProviderCreateRequest,
    _: AuthContext = Depends(require_admin_api_key),
    session: AsyncSession = Depends(get_async_session),
) -> ProviderRead:
    existing = (await session.execute(select(Provider).where(Provider.name == payload.name))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provider name already exists.")

    provider = Provider(
        name=payload.name,
        provider_type=payload.provider_type,
        base_url=payload.base_url,
        api_key=payload.api_key,
        supported_models=payload.supported_models,
        priority=payload.priority,
        weight=payload.weight,
        is_active=payload.is_active,
        timeout_seconds=payload.timeout_seconds,
    )
    session.add(provider)
    await session.flush()
    session.add(ProviderHealth(provider_id=provider.id))
    await session.commit()
    await session.refresh(provider)

    return ProviderRead(
        id=provider.id,
        name=provider.name,
        provider_type=provider.provider_type,
        base_url=provider.base_url,
        supported_models=provider.supported_models,
        priority=provider.priority,
        weight=provider.weight,
        is_active=provider.is_active,
        timeout_seconds=provider.timeout_seconds,
        health_status="healthy",
        consecutive_failures=0,
        circuit_opened_until=None,
    )


@router.post("/pricing")
async def upsert_pricing(
    payload: ModelPricingUpsertRequest,
    _: AuthContext = Depends(require_admin_api_key),
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    if payload.currency != "CNY":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only CNY pricing is supported. Got '{payload.currency}'.",
        )

    provider = (await session.execute(select(Provider).where(Provider.id == payload.provider_id))).scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found.")

    stmt = select(ModelPricing).where(
        ModelPricing.provider_id == payload.provider_id,
        ModelPricing.model_name == payload.model_name,
    )
    pricing = (await session.execute(stmt)).scalar_one_or_none()
    if pricing is None:
        pricing = ModelPricing(
            provider_id=payload.provider_id,
            model_name=payload.model_name,
        )
        session.add(pricing)

    pricing.input_cost_per_1k_tokens = payload.input_cost_per_1k_tokens
    pricing.output_cost_per_1k_tokens = payload.output_cost_per_1k_tokens
    pricing.currency = payload.currency
    pricing.is_active = payload.is_active

    await session.commit()
    return {
        "provider_id": pricing.provider_id,
        "model_name": pricing.model_name,
        "input_cost_per_1k_tokens": str(pricing.input_cost_per_1k_tokens),
        "output_cost_per_1k_tokens": str(pricing.output_cost_per_1k_tokens),
        "currency": pricing.currency,
        "is_active": pricing.is_active,
    }


@router.post("/customers", response_model=CustomerCreateResponse)
async def create_customer(
    payload: CustomerCreateRequest,
    _: AuthContext = Depends(require_admin_api_key),
    session: AsyncSession = Depends(get_async_session),
) -> CustomerCreateResponse:
    existing = (await session.execute(select(User).where(User.name == payload.name))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User name already exists.")

    user = User(name=payload.name, is_admin=False)
    session.add(user)
    await session.flush()

    plain_key = generate_api_key("gw")
    api_key = APIKey(
        user_id=user.id,
        key_hash=hash_api_key(plain_key, settings.gateway_api_key_hash_secret),
        key_prefix=plain_key[:12],
        description=payload.description,
    )
    session.add(api_key)
    await session.flush()

    payment_amount, granted_balance, margin_amount = resolve_topup_amounts(
        payment_amount=payload.payment_amount,
        granted_balance=payload.granted_balance,
        margin_amount=payload.margin_amount,
    )
    session.add(
        apply_topup(
            user=user,
            payment_amount=payment_amount,
            granted_balance=granted_balance,
            margin_amount=margin_amount,
            note="Initial customer funding",
            api_key_id=api_key.id,
        )
    )

    await session.commit()
    return CustomerCreateResponse(
        user_id=user.id,
        api_key_id=api_key.id,
        api_key=plain_key,
        balance=user.balance,
    )


@router.post("/topups", response_model=AdminBalanceResponse)
async def top_up_customer(
    payload: TopUpRequest,
    _: AuthContext = Depends(require_admin_api_key),
    session: AsyncSession = Depends(get_async_session),
) -> AdminBalanceResponse:
    user = (await session.execute(select(User).where(User.id == payload.user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Idempotency check
    idempotency_note = f"topup:{payload.idempotency_key}"
    existing = (
        await session.execute(
            select(BalanceTransaction).where(BalanceTransaction.note == idempotency_note).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate topup request (idempotency_key already used).")

    payment_amount, granted_balance, margin_amount = resolve_topup_amounts(
        payment_amount=payload.payment_amount,
        granted_balance=payload.granted_balance,
        margin_amount=payload.margin_amount,
    )
    session.add(
        apply_topup(
            user=user,
            payment_amount=payment_amount,
            granted_balance=granted_balance,
            margin_amount=margin_amount,
            note=idempotency_note,
        )
    )
    await reactivate_user_api_keys(session, user_id=user.id)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate topup request (idempotency_key already used).",
        )
    active_api_key_count = len(
        list(
            (
                await session.scalars(
                    select(APIKey).where(APIKey.user_id == user.id, APIKey.is_active.is_(True))
                )
            ).all()
        )
    )
    return AdminBalanceResponse(
        user_id=user.id,
        user_name=user.name,
        balance=user.balance,
        active_api_key_count=active_api_key_count,
    )


@router.get("/users", response_model=list[AdminBalanceResponse])
async def list_users(
    _: AuthContext = Depends(require_admin_api_key),
    session: AsyncSession = Depends(get_async_session),
) -> list[AdminBalanceResponse]:
    users = list(
        (
            await session.scalars(
                select(User).options(selectinload(User.api_keys)).order_by(User.created_at.asc())
            )
        ).all()
    )
    return [
        AdminBalanceResponse(
            user_id=user.id,
            user_name=user.name,
            balance=user.balance,
            active_api_key_count=len([item for item in user.api_keys if item.is_active]),
        )
        for user in users
        if not user.is_admin
    ]


@router.get("/usage/users", response_model=list[AdminUserUsageResponse])
async def list_usage_by_user(
    _: AuthContext = Depends(require_admin_api_key),
    session: AsyncSession = Depends(get_async_session),
) -> list[AdminUserUsageResponse]:
    return await get_user_usage_report(session)


@router.get("/usage/models", response_model=list[AdminModelUsageResponse])
async def list_usage_by_model(
    _: AuthContext = Depends(require_admin_api_key),
    session: AsyncSession = Depends(get_async_session),
) -> list[AdminModelUsageResponse]:
    return await get_model_usage_report(session)


@router.get("/ledger/{user_id}", response_model=list[LedgerEntryResponse])
async def get_customer_ledger(
    user_id: str,
    _: AuthContext = Depends(require_admin_api_key),
    session: AsyncSession = Depends(get_async_session),
) -> list[LedgerEntryResponse]:
    user = (await session.execute(select(User).where(User.id == user_id, User.is_admin.is_(False)))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return await get_user_ledger(session, user_id=user_id)
