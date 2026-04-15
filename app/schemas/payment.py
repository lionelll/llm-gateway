from decimal import Decimal

from pydantic import BaseModel, Field


class CheckoutSessionRequest(BaseModel):
    """Client requests a Stripe checkout session for a top-up."""
    amount_cny: Decimal = Field(gt=Decimal("0"), description="Amount to top-up in CNY (e.g. 100.00)")


class CheckoutSessionResponse(BaseModel):
    session_id: str
    checkout_url: str


class TopUpStatusResponse(BaseModel):
    user_id: str
    balance: str
    message: str
