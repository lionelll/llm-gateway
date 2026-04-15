from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.api_key import APIKey
from app.models.balance_transaction import BalanceTransaction
from app.models.usage_log import UsageLog
from app.models.user import User
from app.services.pricing_service import MONEY_QUANTUM, ZERO_MONEY, quantize_money


def resolve_topup_amounts(
    *,
    payment_amount: Decimal | None,
    granted_balance: Decimal | None,
    margin_amount: Decimal | None,
) -> tuple[Decimal, Decimal, Decimal]:
    payment = quantize_money(payment_amount or ZERO_MONEY)
    granted = quantize_money(granted_balance or ZERO_MONEY)
    margin = quantize_money(margin_amount or ZERO_MONEY)

    if granted == ZERO_MONEY and payment > ZERO_MONEY:
        granted = quantize_money(payment - margin)
    elif payment == ZERO_MONEY and granted > ZERO_MONEY:
        payment = quantize_money(granted + margin)
    elif payment > ZERO_MONEY and granted > ZERO_MONEY and margin == ZERO_MONEY:
        margin = quantize_money(payment - granted)

    if granted <= ZERO_MONEY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Granted balance must be greater than 0.00.",
        )

    if payment < granted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment amount cannot be smaller than granted balance.",
        )

    margin = quantize_money(payment - granted)
    return payment, granted, margin


def ensure_sufficient_balance(user: User, required_amount: Decimal, *, model: str) -> None:
    if user.balance < required_amount:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Insufficient balance for model '{model}'. "
                f"Required approximately {required_amount:.2f} CNY, available {user.balance:.2f} CNY."
            ),
        )


def build_topup_transaction(
    *,
    user: User,
    amount: Decimal,
    balance_after: Decimal,
    payment_amount: Decimal,
    margin_amount: Decimal,
    note: str | None = None,
    api_key_id: str | None = None,
) -> BalanceTransaction:
    return BalanceTransaction(
        user_id=user.id,
        api_key_id=api_key_id,
        transaction_type="topup",
        amount=amount,
        balance_after=balance_after,
        payment_amount=payment_amount,
        margin_amount=margin_amount,
        note=note,
    )


def apply_topup(
    *,
    user: User,
    payment_amount: Decimal,
    granted_balance: Decimal,
    margin_amount: Decimal,
    note: str | None = None,
    api_key_id: str | None = None,
) -> BalanceTransaction:
    user.balance = quantize_money(user.balance + granted_balance)
    return build_topup_transaction(
        user=user,
        amount=granted_balance,
        balance_after=user.balance,
        payment_amount=payment_amount,
        margin_amount=margin_amount,
        note=note,
        api_key_id=api_key_id,
    )


async def reactivate_user_api_keys(session: AsyncSession, *, user_id: str) -> None:
    api_keys = list((await session.scalars(select(APIKey).where(APIKey.user_id == user_id))).all())
    for item in api_keys:
        item.is_active = True


def build_usage_transaction(
    *,
    user: User,
    api_key: APIKey,
    usage_log: UsageLog,
    charged_amount: Decimal,
) -> BalanceTransaction:
    return BalanceTransaction(
        user_id=user.id,
        api_key_id=api_key.id,
        usage_log_id=usage_log.id,
        request_id=usage_log.request_id,
        transaction_type="usage_debit",
        amount=charged_amount * Decimal("-1"),
        balance_after=user.balance,
        note=f"Usage charge for {usage_log.model}",
    )


async def apply_usage_charge(
    session: AsyncSession,
    *,
    user: User,
    api_key: APIKey,
    usage_log: UsageLog,
    billed_amount: Decimal,
) -> BalanceTransaction | None:
    settings = get_settings()
    charged_amount = min(user.balance, billed_amount)
    charged_amount = charged_amount.quantize(MONEY_QUANTUM)
    usage_log.billed_amount = charged_amount

    if charged_amount <= ZERO_MONEY:
        return None

    user.balance = quantize_money(user.balance - charged_amount)
    transaction = build_usage_transaction(
        user=user,
        api_key=api_key,
        usage_log=usage_log,
        charged_amount=charged_amount,
    )
    session.add(transaction)
    if settings.auto_disable_api_keys_on_zero_balance and user.balance <= ZERO_MONEY:
        api_keys = list((await session.scalars(select(APIKey).where(APIKey.user_id == user.id))).all())
        for item in api_keys:
            item.is_active = False
    return transaction
