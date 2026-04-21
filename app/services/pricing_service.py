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
    byte_length = len(serialized.encode('utf-8'))
    # UTF-8 byte count is a provable upper bound on BPE token count
    # (each token encodes at least 1 byte). +64 covers chat formatting overhead.
    return max(1, byte_length + 64)


def estimate_max_billable_amount(payload: ChatCompletionRequest, pricing: ModelPricing) -> Decimal:
    """Compute the maximum possible cost for this request.

    max_tokens is enforced at the router entry point, so it is always set.
    The result is a hard ceiling (not an estimate) used for balance pre-freeze.
    Input tokens use 2x padding because the char-based heuristic can undercount.
    Output tokens use the exact max_tokens value (upstream is bound by it).
    """
    estimated_input_tokens = estimate_prompt_tokens(payload)  # byte_length is already an upper bound
    estimated_output_tokens = payload.max_tokens
    assert estimated_output_tokens is not None, "max_tokens must be enforced before estimate"
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
