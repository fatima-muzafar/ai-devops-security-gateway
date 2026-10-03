"""
POST /api/gateway/tool-request -- thin as of Phase 7 Stage 3 (decisions.md #38).

parse -> app.gateway.pipeline -> response. Contract unchanged (the Phase 6
agent depends on it): BLOCK -> {request_id, decision, reason}; ALLOW ->
{request_id, decision, result}. Validation failures are BLOCK decisions (HTTP
200), not HTTP errors (#34). 422 = unparseable body, 409 = duplicate
request_id (#36), 502 = ALLOWED but MCP execution failed.

MUST stay a sync `def` (#26, #37): the Gateway calls MCP over HTTP inside the
same uvicorn process.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.gateway.audit import DuplicateRequestError
from app.gateway.mcp_client import get_mcp_client
from app.gateway.pipeline import ExecutionFailedError, GatewayRequest, handle_tool_request

router = APIRouter()


class ToolRequestIn(BaseModel):
    """Section 17's structured tool-request payload. `arguments` uses
    `service_name` (decisions.md #14). `request_id` max_length=32 matches
    security_requests.request_id String(32) (#36)."""

    request_id: str = Field(..., min_length=1, max_length=32)
    user_id: str = Field(..., min_length=1)
    agent_id: str | None = None
    tool: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.post("/api/gateway/tool-request")
def gateway_tool_request(
    payload: ToolRequestIn,
    db: Session = Depends(get_db),
    mcp_client=Depends(get_mcp_client),
):
    req = GatewayRequest(
        request_id=payload.request_id,
        user_id=payload.user_id,
        agent_id=payload.agent_id,
        tool=payload.tool,
        arguments=payload.arguments,
        raw_request=payload.model_dump(),
    )
    try:
        return handle_tool_request(db, mcp_client, req)
    except DuplicateRequestError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"request_id '{payload.request_id}' already exists; the original request is unchanged.",
        ) from exc
    except ExecutionFailedError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc