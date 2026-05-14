from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from automana.api.dependancies.auth.users import CurrentUserDep
from automana.api.schemas.StandardisedQueryResponse import ApiResponse
from automana.core.repositories.ai.ollama_repository import OllamaAPIRepository
from automana.core.services.ai.agent_chat_service import run_agent_turn
from automana.core.settings import get_settings
from automana.core.utils.redis_cache import get_redis_client

logger = logging.getLogger(__name__)

ai_router = APIRouter(prefix="/ai", tags=["AI Agent"])

settings = get_settings()


class AgentChatRequest(BaseModel):
    message: str
    session_id: str = ""
    app_code: str | None = None


class AgentChatResponse(BaseModel):
    reply: str
    session_id: str
    tools_called: list[str]


@ai_router.post("/chat", response_model=ApiResponse)
async def agent_chat(
    body: AgentChatRequest,
    user: CurrentUserDep,
    request: Request,
) -> ApiResponse:
    session_id = body.session_id or str(uuid.uuid4())

    redis = await get_redis_client()
    ollama_repo = OllamaAPIRepository(base_url=settings.ollama_base_url)

    agent_pool = getattr(request.app.state, "agent_pool", None)
    if agent_pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable",
        )

    try:
        async with agent_pool.acquire() as conn:
            result = await run_agent_turn(
                conn=conn,
                redis=redis,
                ollama_repo=ollama_repo,
                user_id=str(user.unique_id),
                session_id=session_id,
                message=body.message,
                app_code=body.app_code,
            )
    except Exception as e:
        logger.error("agent_chat_error", extra={"error": str(e)}, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable",
        )

    return ApiResponse(
        message="ok",
        data=AgentChatResponse(**result).model_dump(),
    )
