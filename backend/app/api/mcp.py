"""
POST /mcp/tools/execute -- the internal MCP HTTP seam (Section 17, FR-15;
decisions.md #37, #40).

Only the Gateway is meant to call this route, with the shared
X-Internal-Token. This route makes NO security decision: it authenticates the
caller as an internal service, then dispatches via execute_tool(). A failure
here is an execution error (400 / 422 / 500), never an ALLOW/BLOCK decision (#11).

MUST stay a sync `def` (#37): the Gateway will call it over HTTP from inside the
same uvicorn process, and a blocking call from an `async def` handler would
deadlock the event loop.
"""
import hmac
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.database.enums import Environment
from app.mcp.server import MCPError, execute_tool

router = APIRouter()

TOKEN_ENV = "MCP_INTERNAL_TOKEN"

# Keys that would collide with execute_tool()'s own parameters (TypeError -> 500).
_RESERVED_ARGUMENT_KEYS = {"db", "tool_name"}


class McpExecuteIn(BaseModel):
    request_id: str = Field(..., min_length=1, max_length=32)
    tool: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


def require_internal_token(
    x_internal_token: str | None = Header(default=None),
) -> None:
    """Fail closed: every failure mode returns the same generic 403."""
    expected = os.environ.get(TOKEN_ENV, "")  # read at REQUEST time
    forbidden = HTTPException(status_code=403, detail="Forbidden.")
    if not expected or not x_internal_token:
        raise forbidden
    if not hmac.compare_digest(
        x_internal_token.encode("utf-8"), expected.encode("utf-8")
    ):
        raise forbidden


@router.post("/mcp/tools/execute", dependencies=[Depends(require_internal_token)])
def mcp_execute(payload: McpExecuteIn, db: Session = Depends(get_db)):
    arguments = dict(payload.arguments)

    service_name = arguments.pop("service_name", None)
    environment_raw = arguments.pop("environment", None)
    if not service_name or environment_raw is None:
        raise HTTPException(
            status_code=422,
            detail="arguments must include 'service_name' and 'environment'.",
        )

    try:
        environment = Environment(environment_raw)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"'{environment_raw}' is not a valid environment.",
        )

    clashing = _RESERVED_ARGUMENT_KEYS & arguments.keys()
    if clashing:
        raise HTTPException(
            status_code=422,
            detail=f"arguments contain reserved key(s): {sorted(clashing)}.",
        )

    try:
        result = execute_tool(db, payload.tool, service_name, environment, **arguments)
    except ValidationError as exc:
        # Tool-specific arguments rejected by mcp/schemas.py.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MCPError as exc:
        # Unknown/disabled tool or unknown service: a dispatch failure,
        # not a security decision (#11).
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    return {"result": result}