import logging
from decimal import Decimal

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)
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

    # Count how many values were explicitly provided (including 0.00)
    provided = sum(1 for v in (payment_amount, granted_balance, margin_amount) if v is not None)

    if provided == 3:
        # All three provided — verify consistency instead of silently overwriting
        expected_margin = quantize_money(payment - granted)
        if expected_margin != margin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Inconsistent amounts: payment({payment}) - granted({granted}) = {expected_margin}, but margin={margin}.",
            )
    elif granted_balance is None and payment > ZERO_MONEY:
        granted = quantize_money(payment - margin)
    elif payment_amount is None and granted > ZERO_MONEY:
        payment = quantize_money(granted + margin)
    elif payment > ZERO_MONEY and granted > ZERO_MONEY and margin_amount is None:
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

    return payment, granted, quantize_money(payment - granted)


def ensure_sufficient_balance(user: User, required_amount: Decimal, *, model: str) -> None:
    if user.balance < required_amount:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Insufficient balance for model '{model}'. "
                f"Required approximately {required_amount:.2f} CNY, available {user.balance:.2f} CNY."
            ),
        )


async def freeze_balance(
    session: AsyncSession,
    *,
    user: User,
    amount: Decimal,
    model: str,
) -> Decimal:
    """
    Atomically freeze (pre-deduct) estimated cost from user balance.
    Returns the actual frozen amount. Raises 402 if balance is insufficient.
    """
    amount = amount.quantize(MONEY_QUANTUM)
    if amount <= ZERO_MONEY:
        return ZERO_MONEY

    locked_user = (
        await session.execute(
            select(User).where(User.id == user.id).with_for_update()
        )
    ).scalar_one()

    if locked_user.balance < amount:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Insufficient balance for model '{model}'. "
                f"Need ~{amount:.2f}, have {locked_user.balance:.2f} CNY."
            ),
        )

    locked_user.balance = quantize_money(locked_user.balance - amount)
    user.balance = locked_user.balance
    await session.flush()
    return amount


async def settle_balance(
    session: AsyncSession,
    *,
    user: User,
    frozen_amount: Decimal,
    actual_amount: Decimal,
) -> None:
    """
    Settle after upstream call: refund (frozen - actual) back to user.
    If actual > frozen (shouldn't happen normally), no extra deduction — platform eats the diff.
    """
    actual_amount = actual_amount.quantize(MONEY_QUANTUM)
    refund = frozen_amount - actual_amount
    if refund <= ZERO_MONEY:
        return

    locked_user = (
        await session.execute(
            select(User).where(User.id == user.id).with_for_update()
        )
    ).scalar_one()

    locked_user.balance = quantize_money(locked_user.balance + refund)
    user.balance = locked_user.balance


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
    api_keys = list((await session.scalars(
        select(APIKey).where(
            APIKey.user_id == user_id,
            APIKey.disabled_reason == "zero_balance",
        )
    )).all())
    for item in api_keys:
        item.is_active = True
        item.disabled_reason = None


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
    frozen_amount: Decimal = ZERO_MONEY,
) -> BalanceTransaction | None:
    """
    Record the actual usage charge. If balance was pre-frozen, settle the difference.
    If not pre-frozen (legacy path), deduct directly with row lock.
    """
    settings = get_settings()
    actual = billed_amount.quantize(MONEY_QUANTUM)

    if frozen_amount > ZERO_MONEY:
        # Settle the frozen portion first (refund frozen - min(actual, frozen) back to user)
        charged_amount = min(actual, frozen_amount)
        await settle_balance(session, user=user, frozen_amount=frozen_amount, actual_amount=charged_amount)

        if actual > frozen_amount:
            # Supplemental deduction: input token estimates can undercount,
            # so actual cost may exceed the pre-freeze. Deduct the shortfall
            # from the user's remaining balance (like credit-card settlement
            # exceeding pre-auth).
            shortfall = (actual - frozen_amount).quantize(MONEY_QUANTUM)
            locked_user = (
                await session.execute(
                    select(User).where(User.id == user.id).with_for_update()
                )
            ).scalar_one()
            supplement = min(shortfall, locked_user.balance).quantize(MONEY_QUANTUM)
            if supplement > ZERO_MONEY:
                locked_user.balance = quantize_money(locked_user.balance - supplement)
                user.balance = locked_user.balance
                charged_amount += supplement
            remaining_loss = (shortfall - supplement).quantize(MONEY_QUANTUM)
            if remaining_loss > ZERO_MONEY:
                logger.warning(
                    "Actual cost exceeded frozen ceiling for user %s: "
                    "actual=%s frozen=%s supplement=%s platform_loss=%s",
                    user.id, actual, frozen_amount, supplement, remaining_loss,
                )
                session.add(BalanceTransaction(
                    user_id=user.id,
                    api_key_id=api_key.id,
                    usage_log_id=usage_log.id,
                    transaction_type="platform_loss",
                    amount=remaining_loss,
                    balance_after=user.balance,
                    note=f"Unrecovered cost for {usage_log.model}: actual={actual} frozen={frozen_amount}",
                ))
    else:
        # Legacy path: no pre-freeze, lock and deduct now
        locked_user = (
            await session.execute(
                select(User).where(User.id == user.id).with_for_update()
            )
        ).scalar_one()
        charged_amount = min(locked_user.balance, actual)
        charged_amount = charged_amount.quantize(MONEY_QUANTUM)
        if charged_amount > ZERO_MONEY:
            locked_user.balance = quantize_money(locked_user.balance - charged_amount)
            user.balance = locked_user.balance

    usage_log.billed_amount = charged_amount

    if charged_amount <= ZERO_MONEY:
        return None

    transaction = build_usage_transaction(
        user=user,
        api_key=api_key,
        usage_log=usage_log,
        charged_amount=charged_amount,
    )
    session.add(transaction)

    # Check if we need to disable keys
    current_balance = user.balance
    if settings.auto_disable_api_keys_on_zero_balance and current_balance <= ZERO_MONEY:
        api_keys = list((await session.scalars(
            select(APIKey).where(APIKey.user_id == user.id, APIKey.disabled_reason.is_(None))
        )).all())
        for item in api_keys:
            item.is_active = False
            item.disabled_reason = "zero_balance"
    return transaction
