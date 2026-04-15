import json
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_pricing import ModelPricing
from app.schemas.chat import ChatCompletionRequest

RAW_COST_QUANTUM = Decimal("0.000001")
MONEY_QUANTUM = Decimal("0.01")
ZERO_MONEY = Decimal("0.00")


def quantize_raw_cost(value: Decimal) -> Decimal:
    return value.quantize(RAW_COST_QUANTUM, rounding=ROUND_HALF_UP)


def quantize_money(value: Decimal) -> Decimal:
    quantized = value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    if value > ZERO_MONEY and quantized == ZERO_MONEY:
        return MONEY_QUANTUM
    return quantized


async def get_model_pricing(
    session: AsyncSession,
    *,
    provider_id: str,
    model_name: str,
) -> ModelPricing | None:
    stmt = (
        select(ModelPricing)
        .where(
            ModelPricing.provider_id == provider_id,
            ModelPricing.is_active.is_(True),
            or_(ModelPricing.model_name == model_name, ModelPricing.model_name == "*"),
        )
        .order_by(ModelPricing.model_name.desc())
    )
    return (await session.execute(stmt)).scalars().first()


def estimate_prompt_tokens(payload: ChatCompletionRequest) -> int:
    serialized = json.dumps(payload.model_dump(exclude_none=True), ensure_ascii=False)
    return max(1, (len(serialized) // 3) + 32)


def estimate_max_billable_amount(payload: ChatCompletionRequest, pricing: ModelPricing) -> Decimal:
    estimated_input_tokens = estimate_prompt_tokens(payload)
    estimated_output_tokens = payload.max_tokens or 512
    raw_cost = (
        (Decimal(estimated_input_tokens) * pricing.input_cost_per_1k_tokens)
        + (Decimal(estimated_output_tokens) * pricing.output_cost_per_1k_tokens)
    ) / Decimal("1000")
    return quantize_money(quantize_raw_cost(raw_cost))


def compute_usage_cost(usage: dict[str, int] | None, pricing: ModelPricing) -> Decimal:
    usage = usage or {}
    prompt_tokens = Decimal(usage.get("prompt_tokens") or 0)
    completion_tokens = Decimal(usage.get("completion_tokens") or 0)
    raw_cost = (
        (prompt_tokens * pricing.input_cost_per_1k_tokens)
        + (completion_tokens * pricing.output_cost_per_1k_tokens)
    ) / Decimal("1000")
    return quantize_raw_cost(raw_cost)
