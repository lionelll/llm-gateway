"""
Stripe payment endpoints:
  POST /billing/checkout       — create Stripe Checkout session (JWT auth)
  POST /billing/webhook        — receive Stripe webhook events (no auth, signature verified)
  GET  /billing/topup-status   — check latest top-up status (JWT auth)
"""
import logging
from decimal import Decimal

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_async_session
from app.deps import require_jwt_user
from app.models.balance_transaction import BalanceTransaction
from app.models.user import User
from app.schemas.payment import CheckoutSessionRequest, CheckoutSessionResponse, TopUpStatusResponse
from app.services.billing_service import apply_topup, reactivate_user_api_keys

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])

# Margin rate applied to Stripe payments (platform fee). Configurable via env.
_MARGIN_RATE = Decimal("0.10")  # 10 %


def _get_stripe_client() -> stripe.StripeClient:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment service not configured.",
        )
    return stripe.StripeClient(settings.stripe_secret_key)


@router.post("/checkout", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    payload: CheckoutSessionRequest,
    user: User = Depends(require_jwt_user),
) -> CheckoutSessionResponse:
    """
    Create a Stripe Checkout session.

    The user pays `amount_cny` CNY; after 10 % platform margin the credited
    balance is `amount_cny * 0.90`.
    """
    settings = get_settings()
    client = _get_stripe_client()

    # Stripe amounts are in the smallest currency unit (fen for CNY = 0.01)
    amount_fen = int(payload.amount_cny * 100)

    session = client.checkout.sessions.create(
        params={
            "payment_method_types": ["card"],
            "line_items": [
                {
                    "price_data": {
                        "currency": "cny",
                        "product_data": {"name": "LLM Gateway 余额充值"},
                        "unit_amount": amount_fen,
                    },
                    "quantity": 1,
                }
            ],
            "mode": "payment",
            "success_url": settings.stripe_success_url,
            "cancel_url": settings.stripe_cancel_url,
            # Pass user_id so the webhook can credit the right account
            "metadata": {
                "user_id": user.id,
                "payment_amount_cny": str(payload.amount_cny),
            },
        }
    )

    return CheckoutSessionResponse(
        session_id=session.id,
        checkout_url=session.url,
    )


@router.post("/webhook", status_code=200)
async def stripe_webhook(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    stripe_signature: str | None = Header(default=None, alias="stripe-signature"),
) -> dict:
    """
    Receive and verify Stripe webhook events.
    Only `checkout.session.completed` is acted upon.
    """
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured.")

    body = await request.body()
    try:
        event = stripe.WebhookSignature.verify_header(
            body.decode(),
            stripe_signature or "",
            settings.stripe_webhook_secret,
        )
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature.")

    if event["type"] == "checkout.session.completed":
        await _handle_checkout_completed(session, event["data"]["object"])

    return {"received": True}


async def _handle_checkout_completed(session: AsyncSession, checkout_session: dict) -> None:
    metadata = checkout_session.get("metadata") or {}
    user_id: str = metadata.get("user_id", "")
    payment_amount_str: str = metadata.get("payment_amount_cny", "0")
    checkout_id: str = checkout_session.get("id", "")

    if not user_id:
        logger.warning("Stripe webhook missing user_id in metadata")
        return

    # Idempotency: skip if this checkout session was already processed
    note_prefix = f"Stripe checkout {checkout_id}"
    existing = (
        await session.execute(
            select(BalanceTransaction).where(BalanceTransaction.note == note_prefix).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        logger.info("Stripe webhook: checkout %s already processed, skipping", checkout_id)
        return

    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        logger.error("Stripe webhook: user %s not found", user_id)
        return

    payment_amount = Decimal(payment_amount_str)
    margin_amount = (payment_amount * _MARGIN_RATE).quantize(Decimal("0.01"))
    granted_balance = payment_amount - margin_amount

    session.add(
        apply_topup(
            user=user,
            payment_amount=payment_amount,
            granted_balance=granted_balance,
            margin_amount=margin_amount,
            note=note_prefix,
        )
    )
    await reactivate_user_api_keys(session, user_id=user.id)
    await session.commit()
    logger.info("Topped up user %s with %.2f CNY (payment: %.2f)", user_id, granted_balance, payment_amount)


@router.get("/topup-status", response_model=TopUpStatusResponse)
async def topup_status(
    user: User = Depends(require_jwt_user),
) -> TopUpStatusResponse:
    return TopUpStatusResponse(
        user_id=user.id,
        balance=f"{user.balance:.2f}",
        message="Balance is up to date.",
    )
