from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import APIKey
from app.models.balance_transaction import BalanceTransaction
from app.models.provider import Provider
from app.models.request_log import RequestLog
from app.models.usage_log import UsageLog
from app.models.user import User
from app.schemas.admin import AdminModelUsageResponse, AdminUserUsageResponse, LedgerEntryResponse
from app.schemas.billing import (
    DashboardResponse,
    LedgerEntryResponse as BillingLedgerEntryResponse,
    ModelUsageResponse,
    RequestActivityResponse,
    UsageSummaryResponse,
)


def _to_decimal(value: Decimal | None, scale: str) -> Decimal:
    return (value or Decimal("0")).quantize(Decimal(scale))


async def get_active_api_key_counts(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            select(APIKey.user_id, func.count(APIKey.id))
            .where(APIKey.is_active.is_(True))
            .group_by(APIKey.user_id)
        )
    ).all()
    return {user_id: count for user_id, count in rows}


async def get_user_usage_report(session: AsyncSession) -> list[AdminUserUsageResponse]:
    active_key_counts = await get_active_api_key_counts(session)
    rows = (
        await session.execute(
            select(
                User.id,
                User.name,
                User.balance,
                func.count(UsageLog.id),
                func.coalesce(func.sum(UsageLog.prompt_tokens), 0),
                func.coalesce(func.sum(UsageLog.completion_tokens), 0),
                func.coalesce(func.sum(UsageLog.total_tokens), 0),
                func.coalesce(func.sum(UsageLog.estimated_cost), Decimal("0.000000")),
                func.coalesce(func.sum(UsageLog.billed_amount), Decimal("0.00")),
            )
            .outerjoin(UsageLog, UsageLog.user_id == User.id)
            .where(User.is_admin.is_(False))
            .group_by(User.id, User.name, User.balance)
            .order_by(User.created_at.asc())
        )
    ).all()

    return [
        AdminUserUsageResponse(
            user_id=user_id,
            user_name=user_name,
            request_count=request_count,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost=_to_decimal(estimated_cost, "0.000001"),
            billed_amount=_to_decimal(billed_amount, "0.01"),
            remaining_balance=_to_decimal(balance, "0.01"),
            active_api_key_count=active_key_counts.get(user_id, 0),
        )
        for user_id, user_name, balance, request_count, prompt_tokens, completion_tokens, total_tokens, estimated_cost, billed_amount in rows
    ]


async def get_model_usage_report(session: AsyncSession) -> list[AdminModelUsageResponse]:
    rows = (
        await session.execute(
            select(
                Provider.id,
                Provider.name,
                Provider.provider_type,
                UsageLog.model,
                func.count(UsageLog.id),
                func.coalesce(func.sum(UsageLog.prompt_tokens), 0),
                func.coalesce(func.sum(UsageLog.completion_tokens), 0),
                func.coalesce(func.sum(UsageLog.total_tokens), 0),
                func.coalesce(func.sum(UsageLog.estimated_cost), Decimal("0.000000")),
                func.coalesce(func.sum(UsageLog.billed_amount), Decimal("0.00")),
            )
            .join(UsageLog, UsageLog.provider_id == Provider.id)
            .group_by(Provider.id, Provider.name, Provider.provider_type, UsageLog.model)
            .order_by(Provider.name.asc(), UsageLog.model.asc())
        )
    ).all()

    return [
        AdminModelUsageResponse(
            provider_id=provider_id,
            provider_name=provider_name,
            provider_type=provider_type,
            model=model,
            request_count=request_count,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost=_to_decimal(estimated_cost, "0.000001"),
            billed_amount=_to_decimal(billed_amount, "0.01"),
        )
        for provider_id, provider_name, provider_type, model, request_count, prompt_tokens, completion_tokens, total_tokens, estimated_cost, billed_amount in rows
    ]


async def get_user_ledger(session: AsyncSession, *, user_id: str) -> list[LedgerEntryResponse]:
    rows = await _get_user_ledger_rows(session, user_id=user_id)
    return [_build_ledger_entry(row) for row in rows]


async def get_user_usage_summary(session: AsyncSession, *, user_id: str) -> UsageSummaryResponse:
    row = (
        await session.execute(
            select(
                func.count(UsageLog.id),
                func.coalesce(func.sum(UsageLog.prompt_tokens), 0),
                func.coalesce(func.sum(UsageLog.completion_tokens), 0),
                func.coalesce(func.sum(UsageLog.total_tokens), 0),
                func.coalesce(func.sum(UsageLog.estimated_cost), Decimal("0.000000")),
                func.coalesce(func.sum(UsageLog.billed_amount), Decimal("0.00")),
            ).where(UsageLog.user_id == user_id)
        )
    ).one()

    request_count, prompt_tokens, completion_tokens, total_tokens, estimated_cost, billed_amount = row
    return UsageSummaryResponse(
        request_count=request_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost=_to_decimal(estimated_cost, "0.000001"),
        billed_amount=_to_decimal(billed_amount, "0.01"),
    )


async def get_user_model_usage(session: AsyncSession, *, user_id: str, limit: int = 10) -> list[ModelUsageResponse]:
    rows = (
        await session.execute(
            select(
                Provider.id,
                Provider.name,
                Provider.provider_type,
                UsageLog.model,
                func.count(UsageLog.id),
                func.coalesce(func.sum(UsageLog.total_tokens), 0),
                func.coalesce(func.sum(UsageLog.billed_amount), Decimal("0.00")),
            )
            .join(Provider, Provider.id == UsageLog.provider_id)
            .where(UsageLog.user_id == user_id)
            .group_by(Provider.id, Provider.name, Provider.provider_type, UsageLog.model)
            .order_by(
                func.coalesce(func.sum(UsageLog.billed_amount), Decimal("0.00")).desc(),
                func.coalesce(func.sum(UsageLog.total_tokens), 0).desc(),
                UsageLog.model.asc(),
            )
            .limit(limit)
        )
    ).all()

    return [
        ModelUsageResponse(
            provider_id=provider_id,
            provider_name=provider_name,
            provider_type=provider_type,
            model=model,
            request_count=request_count,
            total_tokens=total_tokens,
            billed_amount=_to_decimal(billed_amount, "0.01"),
        )
        for provider_id, provider_name, provider_type, model, request_count, total_tokens, billed_amount in rows
    ]


async def get_user_recent_requests(
    session: AsyncSession,
    *,
    user_id: str,
    limit: int = 12,
) -> list[RequestActivityResponse]:
    rows = (
        await session.execute(
            select(
                RequestLog.request_id,
                RequestLog.model,
                Provider.name,
                Provider.provider_type,
                RequestLog.status_code,
                RequestLog.latency_ms,
                func.coalesce(UsageLog.prompt_tokens, 0),
                func.coalesce(UsageLog.completion_tokens, 0),
                func.coalesce(UsageLog.total_tokens, 0),
                func.coalesce(UsageLog.billed_amount, Decimal("0.00")),
                RequestLog.error_message,
                RequestLog.created_at,
            )
            .select_from(RequestLog)
            .outerjoin(
                UsageLog,
                (UsageLog.request_id == RequestLog.request_id) & (UsageLog.user_id == RequestLog.user_id),
            )
            .outerjoin(Provider, Provider.id == RequestLog.provider_id)
            .where(RequestLog.user_id == user_id, RequestLog.path == "/v1/chat/completions")
            .order_by(RequestLog.created_at.desc())
            .limit(limit)
        )
    ).all()

    return [
        RequestActivityResponse(
            request_id=request_id,
            model=model,
            provider_name=provider_name,
            provider_type=provider_type,
            status_code=status_code,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            billed_amount=_to_decimal(billed_amount, "0.01"),
            error_message=error_message,
            created_at=created_at,
        )
        for request_id, model, provider_name, provider_type, status_code, latency_ms, prompt_tokens, completion_tokens, total_tokens, billed_amount, error_message, created_at in rows
    ]


async def get_user_dashboard(
    session: AsyncSession,
    *,
    user: User,
    key_prefix: str,
    recent_limit: int = 12,
) -> DashboardResponse:
    usage_summary = await get_user_usage_summary(session, user_id=user.id)
    model_usage = await get_user_model_usage(session, user_id=user.id, limit=10)
    recent_requests = await get_user_recent_requests(session, user_id=user.id, limit=recent_limit)
    recent_ledger = [
        _build_billing_ledger_entry(row)
        for row in await _get_user_ledger_rows(session, user_id=user.id, limit=recent_limit)
    ]
    return DashboardResponse(
        user_id=user.id,
        user_name=user.name,
        balance=_to_decimal(user.balance, "0.01"),
        key_prefix=key_prefix,
        is_admin=user.is_admin,
        usage_summary=usage_summary,
        model_usage=model_usage,
        recent_requests=recent_requests,
        recent_ledger=recent_ledger,
    )


async def _get_user_ledger_rows(
    session: AsyncSession,
    *,
    user_id: str,
    limit: int | None = None,
) -> list[BalanceTransaction]:
    rows = list(
        (
            await session.scalars(
                select(BalanceTransaction)
                .where(BalanceTransaction.user_id == user_id)
                .order_by(BalanceTransaction.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
    return rows


def _build_ledger_entry(row: BalanceTransaction) -> LedgerEntryResponse:
    return LedgerEntryResponse(
        id=row.id,
        transaction_type=row.transaction_type,
        amount=_to_decimal(row.amount, "0.01"),
        balance_after=_to_decimal(row.balance_after, "0.01"),
        payment_amount=_to_decimal(row.payment_amount, "0.01") if row.payment_amount is not None else None,
        margin_amount=_to_decimal(row.margin_amount, "0.01") if row.margin_amount is not None else None,
        currency=row.currency,
        note=row.note,
        request_id=row.request_id,
        api_key_id=row.api_key_id,
        created_at=row.created_at,
    )


def _build_billing_ledger_entry(row: BalanceTransaction) -> BillingLedgerEntryResponse:
    return BillingLedgerEntryResponse(
        id=row.id,
        transaction_type=row.transaction_type,
        amount=_to_decimal(row.amount, "0.01"),
        balance_after=_to_decimal(row.balance_after, "0.01"),
        payment_amount=_to_decimal(row.payment_amount, "0.01") if row.payment_amount is not None else None,
        margin_amount=_to_decimal(row.margin_amount, "0.01") if row.margin_amount is not None else None,
        currency=row.currency,
        note=row.note,
        request_id=row.request_id,
        api_key_id=row.api_key_id,
        created_at=row.created_at,
    )
