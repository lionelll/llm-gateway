"""
LangChain model factory and utilities.

Converts between OpenAI-format requests/responses and LangChain types,
and provides both invoke (non-streaming) and stream interfaces.
"""
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.core.exceptions import UpstreamProviderError
from app.models.provider import Provider
from app.schemas.chat import ChatCompletionRequest, ChatMessage

logger = logging.getLogger(__name__)


def _to_langchain_messages(messages: list[ChatMessage]) -> list[BaseMessage]:
    result: list[BaseMessage] = []
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content, ensure_ascii=False)
        if msg.role == "system":
            result.append(SystemMessage(content=content))
        elif msg.role == "assistant":
            result.append(AIMessage(content=content))
        else:
            result.append(HumanMessage(content=content))
    return result


def _build_model(provider: Provider, model_name: str) -> Any:
    """Return the appropriate LangChain chat model for the given provider."""
    ptype = provider.provider_type

    if ptype == "openai":
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {"model": model_name, "temperature": 0}
        if provider.api_key:
            kwargs["api_key"] = provider.api_key
        if provider.base_url:
            # OpenAI client expects base_url to end with /v1
            base = provider.base_url.rstrip("/")
            if not base.endswith("/v1"):
                base = base + "/v1"
            kwargs["base_url"] = base
        kwargs["timeout"] = provider.timeout_seconds
        return ChatOpenAI(**kwargs)

    if ptype == "anthropic":
        from langchain_anthropic import ChatAnthropic

        kwargs = {"model": model_name, "timeout": float(provider.timeout_seconds)}
        if provider.api_key:
            kwargs["api_key"] = provider.api_key
        if provider.base_url and provider.base_url != "https://api.anthropic.com":
            kwargs["base_url"] = provider.base_url.rstrip("/")
        return ChatAnthropic(**kwargs)

    if ptype == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs = {"model": model_name}
        if provider.api_key:
            kwargs["google_api_key"] = provider.api_key
        return ChatGoogleGenerativeAI(**kwargs)

    raise UpstreamProviderError(500, f"Unsupported provider type for LangChain: '{ptype}'", provider=provider)


def _to_openai_response(ai_message: AIMessage, model_name: str, request_id: str) -> dict[str, Any]:
    content = ai_message.content if isinstance(ai_message.content, str) else json.dumps(ai_message.content)
    usage_meta = getattr(ai_message, "usage_metadata", None) or {}
    prompt_tokens = usage_meta.get("input_tokens", 0)
    completion_tokens = usage_meta.get("output_tokens", 0)
    return {
        "id": f"chatcmpl-{request_id}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


async def langchain_invoke(provider: Provider, payload: ChatCompletionRequest) -> tuple[dict[str, Any], int]:
    """Call an LLM provider via LangChain (non-streaming). Returns (openai_format_dict, status_code)."""
    try:
        model = _build_model(provider, payload.model)
        if payload.temperature is not None:
            model = model.bind(temperature=payload.temperature)
        if payload.max_tokens is not None:
            model = model.bind(max_tokens=payload.max_tokens)

        messages = _to_langchain_messages(payload.messages)
        ai_message: AIMessage = await model.ainvoke(messages)  # type: ignore[assignment]
        request_id = uuid4().hex[:24]
        return _to_openai_response(ai_message, payload.model, request_id), 200

    except UpstreamProviderError:
        raise
    except Exception as exc:
        logger.exception("LangChain invoke error for provider %s", provider.name)
        raise UpstreamProviderError(502, f"Provider error: {exc}", provider=provider) from exc


async def langchain_stream(
    provider: Provider,
    payload: ChatCompletionRequest,
) -> AsyncGenerator[str, None]:
    """
    Stream an LLM response as OpenAI-compatible SSE chunks.

    Yields strings like "data: {...}\\n\\n" and ends with "data: [DONE]\\n\\n".
    Also yields a special sentinel line at the very end for token-count capture:
        "data: [USAGE] {\"prompt_tokens\": N, \"completion_tokens\": M}\\n\\n"
    """
    try:
        model = _build_model(provider, payload.model)
        if payload.temperature is not None:
            model = model.bind(temperature=payload.temperature)
        if payload.max_tokens is not None:
            model = model.bind(max_tokens=payload.max_tokens)

        messages = _to_langchain_messages(payload.messages)
        chunk_id = f"chatcmpl-{uuid4().hex[:24]}"
        created = int(time.time())
        prompt_tokens = 0
        completion_tokens = 0

        async for chunk in model.astream(messages):  # type: ignore[union-attr]
            content = chunk.content if isinstance(chunk.content, str) else ""

            # Capture usage metadata when available (usually on the last chunk)
            usage_meta = getattr(chunk, "usage_metadata", None) or {}
            if usage_meta.get("input_tokens"):
                prompt_tokens = usage_meta["input_tokens"]
            if usage_meta.get("output_tokens"):
                completion_tokens = usage_meta["output_tokens"]

            if content:
                data = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": payload.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": content},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        # Final chunk with finish_reason
        final = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": payload.model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(final)}\n\n"

        # Sentinel with token counts for billing (not forwarded to client)
        usage_sentinel = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
        yield f"data: [USAGE] {json.dumps(usage_sentinel)}\n\n"

        yield "data: [DONE]\n\n"

    except UpstreamProviderError:
        raise
    except Exception as exc:
        logger.exception("LangChain stream error for provider %s", provider.name)
        raise UpstreamProviderError(502, f"Provider stream error: {exc}", provider=provider) from exc
