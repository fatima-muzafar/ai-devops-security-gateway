"""
FastAPI application bootstrap (Phase 5).

Phase 5 exists to prove one thing: an HTTP request can reach
`app.mcp.server.execute_tool()` and produce an observable mock-environment
state change, through a single HTTP endpoint with a throwaway decision
rule -- not through the real Security Gateway (Phase 7+).

Everything this route does NOT do is deliberate (STATUS.md Phase 5
Boundary): no authentication, no identity/ownership/environment-policy
checks (Phase 8), no rule risk (Phase 9), no ML (Phase 10), no
APPROVAL_REQUIRED / human approval (Phase 11). The decision rule below is
an explicit, temporary placeholder (STATUS.md Phase 5 Goal) and is
scheduled for full replacement -- not extension -- in Phase 8.
"""
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.database.enums import Environment
from app.mcp.server import MCPError, execute_tool

app = FastAPI(title="Security Gateway FYP -- Phase 5 Skeleton")


class ToolRequestIn(BaseModel):
    """Section 17's structured tool-request payload.

    `arguments` carries the two fields every tool needs to resolve a
    target -- `service_name` and `environment` -- plus any tool-specific
    args (e.g. `target_version` for deploy_service; Section 12 /
    mcp/schemas.py).

    Note: Section 17's own worked example uses the key "service", but the
    schema actually implemented in Phase 4 (mcp/schemas.py,
    ServiceTargetArgs) uses "service_name". This route follows the
    implemented schema, not the doc's older example key, since
    execute_tool() requires service_name to resolve the target Service.
    """

    request_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    agent_id: str | None = None
    tool: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


@app.post("/api/gateway/tool-request")
def gateway_tool_request(payload: ToolRequestIn, db: Session = Depends(get_db)):
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

    # --- Phase 5 placeholder decision rule (STATUS.md Phase 5 Goal) ---
    # This is NOT Section 8's policy engine and NOT ownership/role
    # checking -- it does not look at identity, ownership, or the
    # `policies` table at all. Phase 8 replaces this rule entirely; it
    # is not meant to survive past Phase 5 in any form.
    decision = "BLOCK" if environment == Environment.PRODUCTION else "ALLOW"

    if decision == "BLOCK":
        # Section 5/11: BLOCK means MCP is never called and the mock
        # state does not change. No execute_tool() call on this path.
        return {
            "request_id": payload.request_id,
            "decision": decision,
            "reason": (
                "Phase 5 placeholder rule: production is blocked "
                "unconditionally (not real policy -- see Phase 8)."
            ),
        }

    try:
        result = execute_tool(
            db,
            payload.tool,
            service_name,
            environment,
            **arguments,
        )
    except ValidationError as exc:
        # Malformed tool-specific arguments (mcp/schemas.py rejected them).
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MCPError as exc:
        # Unknown/disabled tool or unknown service -- a dispatch failure,
        # not a security decision (decisions.md #11).
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()

    return {
        "request_id": payload.request_id,
        "decision": decision,
        "result": result,
    }