"""
LangGraph-based routing graph for LLM provider selection with fallback.

Replaces the manual for-loop in proxy_service.py with an explicit state machine:

  START → select_candidate → check_pricing → check_balance → invoke_provider
             ↑                                                      |
             └──────────── (fallback: try next) ───────────────────┘
                                                      ↓ (success)
                                                     END
"""
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import TypedDict

from app.core.exceptions import InsufficientBalanceError, PricingNotConfiguredError, UpstreamProviderError
from app.models.model_pricing import ModelPricing
from app.models.provider import Provider
from app.models.user import User
from app.schemas.chat import ChatCompletionRequest
from app.services.billing_service import freeze_balance, settle_balance
from app.services.langchain_service import langchain_invoke, langchain_stream
from app.services.pricing_service import (
    compute_usage_cost,
    estimate_max_billable_amount,
    get_model_pricing,
    quantize_money,
)
from app.services.provider_health_service import mark_provider_failure, mark_provider_success
from app.services.routing_service import get_provider_candidates

logger = logging.getLogger(__name__)

_FALLBACK_STATUS_CODES = {401, 403, 404, 408, 409, 429}


@dataclass
class ProxyResult:
    provider: Provider
    pricing: ModelPricing | None
    estimated_max_charge: Decimal
    frozen_amount: Decimal
    response_payload: dict[str, Any]
    status_code: int


class RoutingState(TypedDict):
    # Input (set once)
    session: Any  # AsyncSession — not serialisable but fine for in-process graph
    payload: ChatCompletionRequest
    user: User

    # Mutable routing state
    candidates: list[Provider]
    candidate_index: int
    pricing: ModelPricing | None
    estimated_max_charge: Decimal
    frozen_amount: Decimal

    # Output
    result: ProxyResult | None
    last_error: UpstreamProviderError | None
    last_pricing_error: PricingNotConfiguredError | None
    last_balance_error: InsufficientBalanceError | None
    terminal_error: str | None  # set when we give up entirely


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

async def _node_load_candidates(state: RoutingState) -> dict:
    candidates = await get_provider_candidates(state["session"], state["payload"].model)
    return {"candidates": candidates, "candidate_index": 0}


def _node_select_candidate(state: RoutingState) -> dict:
    idx = state["candidate_index"]
    candidates = state["candidates"]
    if idx >= len(candidates):
        # All candidates exhausted — pick terminal error message
        if state.get("last_error"):
            msg = f"All providers failed. Last: {state['last_error'].detail}"
        elif state.get("last_balance_error"):
            msg = state["last_balance_error"].detail
        elif state.get("last_pricing_error"):
            msg = state["last_pricing_error"].detail
        else:
            msg = "No provider available for the requested model."
        return {"terminal_error": msg}
    return {}


async def _node_check_pricing(state: RoutingState) -> dict:
    idx = state["candidate_index"]
    provider = state["candidates"][idx]
    pricing = await get_model_pricing(state["session"], provider_id=provider.id, model_name=state["payload"].model)

    if pricing is None and provider.provider_type != "mock":
        err = PricingNotConfiguredError(
            503,
            f"Pricing not configured for provider '{provider.name}' and model '{state['payload'].model}'.",
        )
        return {"pricing": None, "last_pricing_error": err, "candidate_index": idx + 1}

    estimated_max_charge = Decimal("0.00")
    if pricing is not None:
        estimated_max_charge = estimate_max_billable_amount(state["payload"], pricing)

    return {"pricing": pricing, "estimated_max_charge": estimated_max_charge}


async def _node_check_balance(state: RoutingState) -> dict:
    idx = state["candidate_index"]
    provider = state["candidates"][idx]
    user = state["user"]
    estimated = state.get("estimated_max_charge", Decimal("0.00"))

    if estimated <= Decimal("0.00"):
        return {"frozen_amount": Decimal("0.00")}

    try:
        frozen = await freeze_balance(
            state["session"],
            user=user,
            amount=estimated,
            model=state["payload"].model,
        )
        # Commit freeze as a durable transaction before calling upstream
        await state["session"].commit()
        return {"frozen_amount": frozen}
    except Exception:
        err = InsufficientBalanceError(
            402,
            f"Insufficient balance for '{provider.name}'. Need ~{estimated:.2f}, have {user.balance:.2f} CNY.",
        )
        return {"last_balance_error": err, "candidate_index": idx + 1, "frozen_amount": Decimal("0.00")}


async def _node_invoke_provider(state: RoutingState) -> dict:
    idx = state["candidate_index"]
    provider = state["candidates"][idx]
    payload = state["payload"]

    frozen = state.get("frozen_amount", Decimal("0.00"))

    if provider.provider_type == "mock":
        from app.services.provider_adapter_service import build_mock_response
        response_payload = build_mock_response(payload, provider.name)
        await mark_provider_success(state["session"], provider)
        result = ProxyResult(
            provider=provider,
            pricing=state.get("pricing"),
            estimated_max_charge=state.get("estimated_max_charge", Decimal("0.00")),
            frozen_amount=frozen,
            response_payload=response_payload,
            status_code=200,
        )
        return {"result": result}

    try:
        response_payload, status_code = await langchain_invoke(provider, payload)
        await mark_provider_success(state["session"], provider)
        result = ProxyResult(
            provider=provider,
            pricing=state.get("pricing"),
            estimated_max_charge=state.get("estimated_max_charge", Decimal("0.00")),
            frozen_amount=frozen,
            response_payload=response_payload,
            status_code=status_code,
        )
        return {"result": result}

    except UpstreamProviderError as exc:
        await mark_provider_failure(state["session"], provider, exc.detail)
        should_fallback = exc.status_code in _FALLBACK_STATUS_CODES or exc.status_code >= 500
        if should_fallback:
            # Unfreeze the balance locked for this provider before trying the next one
            if frozen > Decimal("0.00"):
                await settle_balance(
                    state["session"], user=state["user"],
                    frozen_amount=frozen, actual_amount=Decimal("0.00"),
                )
            return {"last_error": exc, "candidate_index": idx + 1, "frozen_amount": Decimal("0.00")}
        return {"last_error": exc, "terminal_error": exc.detail}


# ---------------------------------------------------------------------------
# Routing conditions
# ---------------------------------------------------------------------------

def _route_after_load(state: RoutingState) -> Literal["select", "end"]:
    return "end" if not state["candidates"] else "select"


def _route_after_select(state: RoutingState) -> Literal["check_pricing", "end"]:
    return "end" if state.get("terminal_error") else "check_pricing"


def _route_after_pricing(state: RoutingState) -> Literal["check_balance", "select"]:
    # If pricing check bumped the index, loop back to select
    return "select" if state.get("last_pricing_error") and state.get("pricing") is None else "check_balance"


def _route_after_balance(state: RoutingState) -> Literal["invoke", "select"]:
    return "select" if state.get("last_balance_error") else "invoke"


def _route_after_invoke(state: RoutingState) -> Literal["end", "select"]:
    if state.get("result") or state.get("terminal_error"):
        return "end"
    return "select"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _build_routing_graph():
    g = StateGraph(RoutingState)
    g.add_node("load_candidates", _node_load_candidates)
    g.add_node("select", _node_select_candidate)
    g.add_node("check_pricing", _node_check_pricing)
    g.add_node("check_balance", _node_check_balance)
    g.add_node("invoke", _node_invoke_provider)

    g.set_entry_point("load_candidates")
    g.add_conditional_edges("load_candidates", _route_after_load, {"select": "select", "end": END})
    g.add_conditional_edges("select", _route_after_select, {"check_pricing": "check_pricing", "end": END})
    g.add_conditional_edges("check_pricing", _route_after_pricing, {"check_balance": "check_balance", "select": "select"})
    g.add_conditional_edges("check_balance", _route_after_balance, {"invoke": "invoke", "select": "select"})
    g.add_conditional_edges("invoke", _route_after_invoke, {"end": END, "select": "select"})

    return g.compile()


_routing_graph = _build_routing_graph()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def route_completion(
    session: AsyncSession,
    payload: ChatCompletionRequest,
    user: User,
) -> ProxyResult:
    """Run the routing graph and return a ProxyResult (non-streaming)."""
    initial: RoutingState = {
        "session": session,
        "payload": payload,
        "user": user,
        "candidates": [],
        "candidate_index": 0,
        "pricing": None,
        "estimated_max_charge": Decimal("0.00"),
        "frozen_amount": Decimal("0.00"),
        "result": None,
        "last_error": None,
        "last_pricing_error": None,
        "last_balance_error": None,
        "terminal_error": None,
    }
    final_state: RoutingState = await _routing_graph.ainvoke(initial)  # type: ignore[assignment]

    if final_state.get("result"):
        return final_state["result"]

    # Raise the most specific error
    err_msg = final_state.get("terminal_error") or "No provider available."
    if final_state.get("last_balance_error"):
        raise final_state["last_balance_error"]
    if final_state.get("last_error"):
        raise UpstreamProviderError(502, err_msg, provider=final_state["last_error"].provider)
    raise UpstreamProviderError(503, err_msg)


async def route_stream(
    session: AsyncSession,
    payload: ChatCompletionRequest,
    user: User,
) -> tuple[Provider, ModelPricing | None, Decimal, Decimal, AsyncGenerator[str, None]]:
    """
    Select a provider via the routing graph, then return a streaming generator.

    Returns (provider, pricing, estimated_max_charge, frozen_amount, sse_generator).
    The caller is responsible for billing after the stream ends.
    """
    candidates = await get_provider_candidates(session, payload.model)
    if not candidates:
        raise UpstreamProviderError(503, f"No active provider available for model '{payload.model}'.")

    last_error: UpstreamProviderError | None = None
    last_pricing_error: PricingNotConfiguredError | None = None
    last_balance_error: InsufficientBalanceError | None = None

    for provider in candidates:
        if provider.provider_type == "mock":
            from app.services.provider_adapter_service import build_mock_response
            import json as _json

            async def _mock_stream(p=provider):
                resp = build_mock_response(payload, p.name)
                content = resp["choices"][0]["message"]["content"]
                usage = resp.get("usage", {})
                import time as _time
                chunk_id = f"chatcmpl-mock-{p.id[:12]}"
                created = int(_time.time())
                data = {
                    "id": chunk_id, "object": "chat.completion.chunk", "created": created,
                    "model": payload.model,
                    "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
                }
                yield f"data: {_json.dumps(data)}\n\n"
                final = {"id": chunk_id, "object": "chat.completion.chunk", "created": created,
                         "model": payload.model,
                         "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                yield f"data: {_json.dumps(final)}\n\n"
                yield f"data: [USAGE] {_json.dumps(usage)}\n\n"
                yield "data: [DONE]\n\n"

            return provider, None, Decimal("0.00"), Decimal("0.00"), _mock_stream()

        pricing = await get_model_pricing(session, provider_id=provider.id, model_name=payload.model)
        if pricing is None:
            last_pricing_error = PricingNotConfiguredError(
                503, f"Pricing not configured for '{provider.name}' / '{payload.model}'."
            )
            continue

        estimated = estimate_max_billable_amount(payload, pricing)

        # Freeze balance atomically before calling upstream
        try:
            frozen = await freeze_balance(session, user=user, amount=estimated, model=payload.model)
            await session.commit()  # persist freeze as durable transaction
        except Exception:
            last_balance_error = InsufficientBalanceError(
                402,
                f"Insufficient balance for '{provider.name}'. Need ~{estimated:.2f}, have {user.balance:.2f} CNY.",
            )
            continue

        try:
            gen = langchain_stream(provider, payload)
            return provider, pricing, estimated, frozen, gen
        except UpstreamProviderError as exc:
            # Unfreeze the balance locked for this provider before trying the next one
            if frozen > Decimal("0.00"):
                await settle_balance(session, user=user, frozen_amount=frozen, actual_amount=Decimal("0.00"))
            await mark_provider_failure(session, provider, exc.detail)
            last_error = exc
            if exc.status_code not in _FALLBACK_STATUS_CODES and exc.status_code < 500:
                raise

    if last_balance_error:
        raise last_balance_error
    if last_error:
        raise UpstreamProviderError(502, f"All providers failed. Last: {last_error.detail}", provider=last_error.provider)
    if last_pricing_error:
        raise last_pricing_error
    raise UpstreamProviderError(503, "No provider available.")
