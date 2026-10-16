"""
Execution of an APPROVED request (decisions.md #84, #85, #89). No HTTP framework code.

Order (#35): the human decision and the revalidation result are already committed by
approvals.service.process_decision(). Only if revalidation passed does this module call MCP,
then update execution_status and resolve the one `pending` behavior event (#85).
"""
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.approvals.service import ApprovalOutcome
from app.database.enums import EventOutcome, ExecutionStatus
from app.database.models import SecurityRequest, Tool
from app.gateway import audit
from app.gateway.behavior_log import resolve_pending_event
from app.gateway.mcp_client import McpUnavailableError


class ApprovalExecutionFailedError(Exception):
    """Approved and revalidated, but MCP failed. Mapped to HTTP 502 (#34, #89)."""


@dataclass(frozen=True)
class ExecutionResult:
    outcome: str  # "rejected" | "revalidation_failed" | "executed"
    reason: str | None = None
    result: Any = None


def finish_decision(db: Session, mcp_client, outcome: ApprovalOutcome) -> ExecutionResult:
    approval = outcome.approval
    request_id = approval.request_id

    if outcome.revalidation is None:  # rejected: revalidation never ran (#84)
        resolve_pending_event(db, request_id, EventOutcome.BLOCKED)
        return ExecutionResult("rejected")

    if not outcome.revalidation.ok:
        resolve_pending_event(db, request_id, EventOutcome.BLOCKED)
        return ExecutionResult("revalidation_failed", reason=outcome.revalidation.reason)

    sec = db.get(SecurityRequest, request_id)
    tool = db.get(Tool, sec.tool_id)
    try:
        response = mcp_client.execute(request_id, tool.tool_name, dict(sec.arguments))
    except McpUnavailableError as exc:
        audit.mark_execution(db, request_id, ExecutionStatus.FAILED)
        resolve_pending_event(db, request_id, EventOutcome.FAILED)
        raise ApprovalExecutionFailedError(
            f"MCP execution failed: MCP unavailable (request {request_id})."
        ) from exc

    if response.status_code != 200:
        detail = str(response.body.get("detail", ""))[:200]
        audit.mark_execution(db, request_id, ExecutionStatus.FAILED)
        resolve_pending_event(db, request_id, EventOutcome.FAILED)
        raise ApprovalExecutionFailedError(
            f"MCP execution failed (HTTP {response.status_code}): {detail}"
        )

    audit.mark_execution(db, request_id, ExecutionStatus.EXECUTED)
    result = response.body.get("result")
    resolve_pending_event(db, request_id, EventOutcome.ALLOWED, result=result)
    return ExecutionResult("executed", result=result)
