from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProviderCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    provider_type: str
    base_url: str
    api_key: str | None = None
    supported_models: list[str]
    priority: int = 0
    weight: int = 1
    is_active: bool = True
    timeout_seconds: int = Field(default=30, ge=1, le=300)


class ModelPricingUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    model_name: str
    input_cost_per_1k_tokens: Decimal = Field(ge=Decimal("0.000000"))
    output_cost_per_1k_tokens: Decimal = Field(ge=Decimal("0.000000"))
    currency: str = "CNY"
    is_active: bool = True


class CustomerCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    payment_amount: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    granted_balance: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    margin_amount: Decimal | None = Field(default=None, ge=Decimal("0.00"))


class CustomerCreateResponse(BaseModel):
    user_id: str
    api_key_id: str
    api_key: str
    balance: Decimal
    currency: str = "CNY"


class TopUpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    payment_amount: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    granted_balance: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    margin_amount: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    note: str | None = None


class AdminBalanceResponse(BaseModel):
    user_id: str
    user_name: str
    balance: Decimal
    active_api_key_count: int = 0
    currency: str = "CNY"


class AdminUserUsageResponse(BaseModel):
    user_id: str
    user_name: str
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: Decimal
    billed_amount: Decimal
    remaining_balance: Decimal
    active_api_key_count: int
    currency: str = "CNY"


class AdminModelUsageResponse(BaseModel):
    provider_id: str
    provider_name: str
    provider_type: str
    model: str
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: Decimal
    billed_amount: Decimal
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
