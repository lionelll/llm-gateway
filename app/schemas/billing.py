from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class BalanceResponse(BaseModel):
    user_id: str
    user_name: str
    balance: Decimal
    currency: str = "CNY"
    key_prefix: str


class PortalLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_name: str
    api_key: str


class UsageSummaryResponse(BaseModel):
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: Decimal
    billed_amount: Decimal
    currency: str = "CNY"


class ModelUsageResponse(BaseModel):
    provider_id: str
    provider_name: str
    provider_type: str
    model: str
    request_count: int
    total_tokens: int
    billed_amount: Decimal
    currency: str = "CNY"


class RequestActivityResponse(BaseModel):
    request_id: str
    model: str
    provider_name: str | None = None
    provider_type: str | None = None
    status_code: int
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    billed_amount: Decimal
    error_message: str | None = None
    created_at: datetime
    currency: str = "CNY"


class LedgerEntryResponse(BaseModel):
    id: str
    transaction_type: str
    amount: Decimal
    balance_after: Decimal
    payment_amount: Decimal | None = None
    margin_amount: Decimal | None = None
    currency: str = "CNY"
    note: str | None = None
    request_id: str | None = None
    api_key_id: str | None = None
    created_at: datetime


class DashboardResponse(BaseModel):
    user_id: str
    user_name: str
    balance: Decimal
    currency: str = "CNY"
    key_prefix: str
    is_admin: bool
    usage_summary: UsageSummaryResponse
    model_usage: list[ModelUsageResponse]
    recent_requests: list[RequestActivityResponse]
    recent_ledger: list[LedgerEntryResponse]
