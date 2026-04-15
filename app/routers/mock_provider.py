from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.schemas.chat import ChatCompletionRequest
from app.services.provider_adapter_service import build_mock_response

router = APIRouter(prefix="/mock", tags=["mock"])


@router.post("/v1/chat/completions")
async def mock_chat_completion(payload: ChatCompletionRequest) -> dict:
    settings = get_settings()
    if not settings.enable_mock_provider:
        raise HTTPException(status_code=404, detail="Mock provider is disabled.")
    return build_mock_response(payload, provider_name="local-http-mock")
