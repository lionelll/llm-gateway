import json
import logging
import time
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import GatewayError, UpstreamProviderError
from app.db import get_async_session
from app.deps import AuthContext, require_api_key
from app.redis_client import get_redis_client
from app.schemas.chat import ChatCompletionRequest
from app.services.auth_service import mark_api_key_used
from app.services.billing_service import apply_usage_charge
from app.services.logging_service import create_request_log, create_usage_log
from app.services.pricing_service import compute_usage_cost, quantize_money
from app.services.provider_health_service import mark_provider_failure, mark_provider_success
from app.services.proxy_service import proxy_chat_completion, proxy_chat_completion_stream
from app.services.rate_limit_service import enforce_rate_limits

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    payload: ChatCompletionRequest,
    request: Request,
    auth: AuthContext = Depends(require_api_key),
    session: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis_client),
):
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limits(redis, auth.api_key.id, client_ip)

    if payload.stream:
        return await _handle_stream(payload, request, auth, session, client_ip)
    return await _handle_non_stream(payload, request, auth, session, client_ip)


# ---------------------------------------------------------------------------
# Non-streaming path
# ---------------------------------------------------------------------------

async def _handle_non_stream(
    payload: ChatCompletionRequest,
    request: Request,
    auth: AuthContext,
    session: AsyncSession,
    client_ip: str,
) -> JSONResponse:
    request_id = str(uuid4())
    started_at = time.perf_counter()

    provider_id: str | None = None
    status_code = 500
    error_message: str | None = None
    remaining_balance = auth.user.balance

    try:
        proxy_result = await proxy_chat_completion(session, payload, auth.user)
        provider_id = proxy_result.provider.id
        status_code = proxy_result.status_code
        mark_api_key_used(auth.api_key)

        session.add(
            create_request_log(
                request_id=request_id,
                user_id=auth.user.id,
                api_key_id=auth.api_key.id,
                provider_id=provider_id,
                model=payload.model,
                path=str(request.url.path),
                method=request.method,
                client_ip=client_ip,
                status_code=status_code,
                latency_ms=int((time.perf_counter() - started_at) * 1000),
            )
        )

        usage = (
            proxy_result.response_payload.get("usage")
            if isinstance(proxy_result.response_payload, dict)
            else None
        )
        estimated_cost = Decimal("0.000000")
        billed_amount = Decimal("0.00")
        if proxy_result.pricing is not None:
            estimated_cost = compute_usage_cost(usage, proxy_result.pricing)
            billed_amount = quantize_money(estimated_cost)

        usage_log = create_usage_log(
            request_id=request_id,
            user_id=auth.user.id,
            provider_id=provider_id,
            model=payload.model,
            usage=usage,
            estimated_cost=estimated_cost,
            billed_amount=billed_amount,
        )
        session.add(usage_log)
        await session.flush()
        await apply_usage_charge(
            session,
            user=auth.user,
            api_key=auth.api_key,
            usage_log=usage_log,
            billed_amount=billed_amount,
        )
        remaining_balance = auth.user.balance
        await session.commit()

        response = JSONResponse(status_code=status_code, content=proxy_result.response_payload)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Balance-Remaining"] = f"{remaining_balance:.2f}"
        return response

    except UpstreamProviderError as exc:
        provider_id = exc.provider.id if exc.provider else None
        status_code = exc.status_code
        error_message = exc.detail
    except GatewayError as exc:
        status_code = exc.status_code
        error_message = exc.detail
    except HTTPException as exc:
        status_code = exc.status_code
        error_message = str(exc.detail)
    except Exception:
        logger.exception("Unexpected error in non-streaming chat completion request_id=%s", request_id)
        error_message = "Unexpected gateway error."
        status_code = 500
        provider_id = None
    finally:
        if status_code >= 400:
            session.add(
                create_request_log(
                    request_id=request_id,
                    user_id=auth.user.id,
                    api_key_id=auth.api_key.id,
                    provider_id=provider_id,
                    model=payload.model,
                    path=str(request.url.path),
                    method=request.method,
                    client_ip=client_ip,
                    status_code=status_code,
                    latency_ms=int((time.perf_counter() - started_at) * 1000),
                    error_message=error_message,
                )
            )
            await session.commit()

    raise HTTPException(status_code=status_code, detail=error_message or "Gateway request failed.")


# ---------------------------------------------------------------------------
# Streaming path
# ---------------------------------------------------------------------------

async def _handle_stream(
    payload: ChatCompletionRequest,
    request: Request,
    auth: AuthContext,
    session: AsyncSession,
    client_ip: str,
) -> StreamingResponse:
    request_id = str(uuid4())
    started_at = time.perf_counter()

    try:
        provider, pricing, estimated_max_charge, sse_gen = await proxy_chat_completion_stream(
            session, payload, auth.user
        )
    except (UpstreamProviderError, GatewayError, HTTPException):
        raise
    except Exception:
        logger.exception("Failed to select provider for streaming request_id=%s", request_id)
        raise HTTPException(status_code=500, detail="Unexpected gateway error.")

    mark_api_key_used(auth.api_key)

    # Capture references for billing closure
    user = auth.user
    api_key = auth.api_key
    provider_id = provider.id

    async def _generate():
        accumulated_usage: dict = {"prompt_tokens": 0, "completion_tokens": 0}
        stream_ok = True
        try:
            async for line in sse_gen:
                # Intercept our billing sentinel — don't forward to client
                if line.startswith("data: [USAGE]"):
                    try:
                        raw = line.removeprefix("data: [USAGE]").strip()
                        accumulated_usage.update(json.loads(raw))
                    except Exception:
                        pass
                    continue
                yield line

        except Exception:
            logger.exception("Streaming error request_id=%s provider=%s", request_id, provider.name)
            stream_ok = False
            err_chunk = json.dumps({"error": {"message": "Stream interrupted", "type": "gateway_error"}})
            yield f"data: {err_chunk}\n\n"

        finally:
            # --- Mark provider health after stream ends ---
            if stream_ok:
                await mark_provider_success(session, provider)
            else:
                await mark_provider_failure(session, provider, "Stream interrupted")

            # --- Billing after stream ends ---
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            final_status = 200 if stream_ok else 500
            try:
                estimated_cost = Decimal("0.000000")
                billed_amount = Decimal("0.00")
                if pricing is not None:
                    estimated_cost = compute_usage_cost(accumulated_usage, pricing)
                    billed_amount = quantize_money(estimated_cost)

                usage_log = create_usage_log(
                    request_id=request_id,
                    user_id=user.id,
                    provider_id=provider_id,
                    model=payload.model,
                    usage=accumulated_usage,
                    estimated_cost=estimated_cost,
                    billed_amount=billed_amount,
                )
                session.add(usage_log)
                session.add(
                    create_request_log(
                        request_id=request_id,
                        user_id=user.id,
                        api_key_id=api_key.id,
                        provider_id=provider_id,
                        model=payload.model,
                        path=request.url.path,
                        method=request.method,
                        client_ip=client_ip,
                        status_code=final_status,
                        latency_ms=latency_ms,
                    )
                )
                await session.flush()
                await apply_usage_charge(
                    session,
                    user=user,
                    api_key=api_key,
                    usage_log=usage_log,
                    billed_amount=billed_amount,
                )
                await session.commit()
            except Exception:
                logger.exception("Billing error after stream request_id=%s", request_id)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "X-Request-ID": request_id,
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
