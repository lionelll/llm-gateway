from decimal import Decimal
from typing import Any

from app.models.request_log import RequestLog
from app.models.usage_log import UsageLog


def create_request_log(
    *,
    request_id: str,
    user_id: str | None,
    api_key_id: str | None,
    provider_id: str | None,
    model: str,
    path: str,
    method: str,
    client_ip: str,
    status_code: int,
    latency_ms: int,
    error_message: str | None = None,
) -> RequestLog:
    return RequestLog(
        request_id=request_id,
        user_id=user_id,
        api_key_id=api_key_id,
        provider_id=provider_id,
        model=model,
        path=path,
        method=method,
        client_ip=client_ip,
        status_code=status_code,
        latency_ms=latency_ms,
        error_message=error_message[:500] if error_message else None,
    )


def create_usage_log(
    *,
    request_id: str,
    user_id: str,
    provider_id: str,
    model: str,
    usage: dict[str, Any] | None,
    estimated_cost: Decimal,
    billed_amount: Decimal,
    currency: str = "CNY",
) -> UsageLog:
    usage = usage or {}
    return UsageLog(
        request_id=request_id,
        user_id=user_id,
        provider_id=provider_id,
        model=model,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
        estimated_cost=estimated_cost,
        billed_amount=billed_amount,
        currency=currency,
    )
