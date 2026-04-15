import json
import time
from typing import Any
from uuid import uuid4

import httpx

from app.core.exceptions import UpstreamProviderError
from app.models.provider import Provider
from app.schemas.chat import ChatCompletionRequest


def build_mock_response(payload: ChatCompletionRequest, provider_name: str) -> dict[str, Any]:
    latest_user_message = ""
    for message in reversed(payload.messages):
        if message.role == "user":
            latest_user_message = str(message.content)
            break

    completion_text = f"[mock:{provider_name}] {latest_user_message or 'Hello from the mock provider.'}"
    prompt_tokens = max(1, len(json.dumps(payload.model_dump(exclude_none=True), ensure_ascii=False)) // 4)
    completion_tokens = max(1, len(completion_text) // 4)

    return {
        "id": f"chatcmpl-mock-{uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": completion_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
            else:
                text_parts.append(json.dumps(item, ensure_ascii=False))
        return "\n".join(part for part in text_parts if part)
    if isinstance(content, dict) and content.get("type") == "text":
        return str(content.get("text", ""))
    return json.dumps(content, ensure_ascii=False)


def build_anthropic_request_payload(payload: ChatCompletionRequest) -> dict[str, Any]:
    system_messages = [_extract_text_content(message.content) for message in payload.messages if message.role == "system"]
    request_messages: list[dict[str, Any]] = []

    for message in payload.messages:
        if message.role == "system":
            continue
        request_messages.append(
            {
                "role": message.role,
                "content": _extract_text_content(message.content),
            }
        )

    anthropic_payload: dict[str, Any] = {
        "model": payload.model,
        "messages": request_messages,
        "max_tokens": payload.max_tokens or 512,
    }
    if system_messages:
        anthropic_payload["system"] = "\n\n".join(system_messages)
    if payload.temperature is not None:
        anthropic_payload["temperature"] = payload.temperature

    return anthropic_payload


def normalize_anthropic_response(response_payload: dict[str, Any], requested_model: str) -> dict[str, Any]:
    content_blocks = response_payload.get("content", [])
    completion_text = "\n".join(
        str(block.get("text", "")) for block in content_blocks if isinstance(block, dict) and block.get("type") == "text"
    )
    usage = response_payload.get("usage", {})
    prompt_tokens = usage.get("input_tokens", 0)
    completion_tokens = usage.get("output_tokens", 0)

    return {
        "id": response_payload.get("id", f"chatcmpl-anthropic-{uuid4().hex[:24]}"),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": response_payload.get("model", requested_model),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": completion_text,
                },
                "finish_reason": response_payload.get("stop_reason", "stop"),
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


async def _perform_json_request(
    *,
    provider: Provider,
    url: str,
    headers: dict[str, str],
    request_body: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    try:
        async with httpx.AsyncClient(timeout=provider.timeout_seconds) as client:
            response = await client.post(url, json=request_body, headers=headers)
    except httpx.TimeoutException as exc:
        raise UpstreamProviderError(504, f"Provider timeout: {provider.name}", provider=provider) from exc
    except httpx.HTTPError as exc:
        raise UpstreamProviderError(502, f"Provider network error: {provider.name}", provider=provider) from exc

    try:
        payload_json = response.json()
    except ValueError as exc:
        raise UpstreamProviderError(502, f"Provider returned non-JSON response: {provider.name}", provider=provider) from exc

    if response.status_code >= 400:
        detail = None
        if isinstance(payload_json, dict):
            error = payload_json.get("error")
            if isinstance(error, dict):
                detail = error.get("message")
            elif isinstance(error, str):
                detail = error
        detail = detail or f"Provider returned HTTP {response.status_code}"
        raise UpstreamProviderError(response.status_code, detail, provider=provider)

    return payload_json, response.status_code


async def call_openai_provider(provider: Provider, payload: ChatCompletionRequest) -> tuple[dict[str, Any], int]:
    url = provider.base_url.rstrip("/") + "/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    return await _perform_json_request(
        provider=provider,
        url=url,
        headers=headers,
        request_body=payload.model_dump(exclude_none=True),
    )


async def call_anthropic_provider(provider: Provider, payload: ChatCompletionRequest) -> tuple[dict[str, Any], int]:
    url = provider.base_url.rstrip("/") + "/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    if provider.api_key:
        headers["x-api-key"] = provider.api_key

    response_payload, status_code = await _perform_json_request(
        provider=provider,
        url=url,
        headers=headers,
        request_body=build_anthropic_request_payload(payload),
    )
    return normalize_anthropic_response(response_payload, payload.model), status_code


async def call_gemini_provider(provider: Provider, payload: ChatCompletionRequest) -> tuple[dict[str, Any], int]:
    """Call Google Gemini via LangChain (Gemini has no OpenAI-compatible REST endpoint)."""
    from app.services.langchain_service import langchain_invoke
    return await langchain_invoke(provider, payload)


async def call_provider(provider: Provider, payload: ChatCompletionRequest) -> tuple[dict[str, Any], int]:
    if provider.provider_type == "mock" or provider.base_url == "mock://local":
        return build_mock_response(payload, provider.name), 200
    if provider.provider_type == "openai":
        return await call_openai_provider(provider, payload)
    if provider.provider_type == "anthropic":
        return await call_anthropic_provider(provider, payload)
    if provider.provider_type == "gemini":
        return await call_gemini_provider(provider, payload)
    raise UpstreamProviderError(500, f"Unsupported provider type '{provider.provider_type}'.", provider=provider)
