"""
POST /api/chat -- developer <-> DevOps agent (Section 17, decisions.md #18).

- request_id is generated HERE, not by the agent (#20), as uuid4().hex so it
  fits security_requests.request_id String(32) (#2, #27).
- user_id is an unvalidated placeholder (#19); Phase 8 replaces it.
- MUST stay a sync `def` (#26): the agent makes a blocking HTTP call back
  into this same app, which would deadlock inside an `async def` handler.
"""
import logging
import uuid
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agent.devops_agent import AgentLLMError, DevOpsAgent
from app.agent.gateway_client import GatewayClient, build_default_http_client
from app.agent.llm import build_gemini_llm

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatIn(BaseModel):
    user_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class ChatOut(BaseModel):
    request_id: str
    reply: str
    # What the agent PROPOSED to the Gateway (None if no tool was needed).
    tool_request: dict[str, Any] | None = None
    # The Gateway's decision, or None if no tool was proposed / the Gateway
    # returned an HTTP error instead of a decision.
    decision: str | None = None


@lru_cache(maxsize=1)
def get_agent() -> DevOpsAgent:
    """Process-wide agent (holds in-memory history, #29). Tests override
    this via app.dependency_overrides."""
    return DevOpsAgent(build_gemini_llm(), GatewayClient(build_default_http_client()))


@router.post("/api/chat", response_model=ChatOut)
def chat(payload: ChatIn, agent: DevOpsAgent = Depends(get_agent)):
    request_id = uuid.uuid4().hex
    try:
        result = agent.handle_message(
            user_id=payload.user_id,
            request_id=request_id,
            message=payload.message,
        )
    except AgentLLMError as exc:
        # Only raised when the FIRST LLM call failed -- nothing was executed
        # (#27). Detail is logged, not returned.
        logger.error("LLM call failed for %s: %s", request_id, exc)
        raise HTTPException(
            status_code=502,
            detail=f"The language model is unavailable (request {request_id}). Nothing was executed.",
        ) from exc

    return ChatOut(
        request_id=request_id,
        reply=result.reply,
        tool_request=result.tool_request,
        decision=result.decision,
    )