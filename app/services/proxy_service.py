"""
proxy_service.py — thin shim that delegates to the LangGraph router.

Non-streaming path:  proxy_chat_completion()  → ProxyResult
Streaming path:      proxy_chat_completion_stream() → (provider, pricing, estimated, sse_generator)

Both are backed by langgraph_router which handles candidate selection,
pricing checks, balance checks, provider invocation, and fallback.
"""
from collections.abc import AsyncGenerator
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_pricing import ModelPricing
from app.models.provider import Provider
from app.models.user import User
from app.schemas.chat import ChatCompletionRequest
from app.services.langgraph_router import ProxyResult, route_completion, route_stream


async def proxy_chat_completion(
    session: AsyncSession,
    payload: ChatCompletionRequest,
    user: User,
) -> ProxyResult:
    """Route a non-streaming chat completion through the LangGraph provider graph."""
    return await route_completion(session, payload, user)


async def proxy_chat_completion_stream(
    session: AsyncSession,
    payload: ChatCompletionRequest,
    user: User,
) -> tuple[Provider, ModelPricing | None, Decimal, Decimal, AsyncGenerator[str, None]]:
    """
    Select a provider and return a streaming SSE generator.

    Returns (provider, pricing, estimated_max_charge, frozen_amount, sse_generator).
    The router yields SSE lines; the last meaningful line before [DONE] is:
        data: [USAGE] {"prompt_tokens": N, "completion_tokens": M}
    The caller strips this sentinel and uses it for billing.
    """
    return await route_stream(session, payload, user)
