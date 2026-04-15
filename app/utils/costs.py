from decimal import Decimal
from typing import Any


def estimate_cost(usage: dict[str, Any] | None) -> Decimal:
    usage = usage or {}
    total_tokens = usage.get("total_tokens") or 0
    return (Decimal(total_tokens) * Decimal("0.000001")).quantize(Decimal("0.000001"))
