"""
Gateway pipeline orchestrator (Section 8; decisions.md #31, #34, #35, #38, #41).

evaluate() is READ-ONLY and short-circuits on the first failing stage:
identity -> tool registry -> arguments -> service -> placeholder policy.
handle_tool_request() then writes the single audit row (committed BEFORE any
MCP call) and, on ALLOW only, calls MCP over HTTP and records the outcome.

Not here (still deferred): JWT, real policy, rule risk, ML, approval/TOCTOU,
behavior_events / risk_assessments writes.
"""
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.database.enums import Decision, Environment, ExecutionStatus
from app.gateway import audit
from app.gateway.identity import resolve_identity
from app.gateway.mcp_client import McpUnavailableError
from app.gateway.policy import evaluate_placeholder_policy
from app.gateway.validation import check_arguments, check_tool_registry, resolve_service

logger = logging.getLogger(__name__)


class ExecutionFailedError(Exception):
    """ALLOWED request whose MCP execution failed. Mapped to HTTP 502 (#34)."""


@dataclass(frozen=True)
class GatewayRequest:
    request_id: str
    user_id: str
    agent_id: str | None
    tool: str
    arguments: dict[str, Any]
    raw_request: dict[str, Any]


@dataclass
class Verdict:
    decision: Decision
    reason: str | None = None
    user_id: int | None = None
    agent_id: int | None = None
    tool_id: int | None = None
    service_id: int | None = None
    environment: Environment | None = None


def evaluate(db: Session, req: GatewayRequest) -> Verdict:
    ident = resolve_identity(db, req.user_id, req.agent_id)
    resolved: dict[str, Any] = {"user_id": ident.user_id, "agent_id": ident.agent_id}
    if ident.block_reason:
        return Verdict(Decision.BLOCK, ident.block_reason, **resolved)

    tool = check_tool_registry(db, req.tool)
    resolved["tool_id"] = tool.tool_id
    if tool.block_reason:
        return Verdict(Decision.BLOCK, tool.block_reason, **resolved)

    args = check_arguments(req.tool, req.arguments)
    resolved["environment"] = args.environment
    if args.block_reason:
        return Verdict(Decision.BLOCK, args.block_reason, **resolved)

    service = resolve_service(db, args.service_name, args.environment)
    resolved["service_id"] = service.service_id
    if service.block_reason:
        return Verdict(Decision.BLOCK, service.block_reason, **resolved)

    policy_reason = evaluate_placeholder_policy(args.environment)
    if policy_reason:
        return Verdict(Decision.BLOCK, policy_reason, **resolved)

    return Verdict(Decision.ALLOW, None, **resolved)


def handle_tool_request(db: Session, mcp_client, req: GatewayRequest) -> dict[str, Any]:
    verdict = evaluate(db, req)

    # One audit INSERT, committed BEFORE any MCP call (#35). A duplicate
    # request_id raises DuplicateRequestError here, before MCP is reachable.
    audit.record_decision(db, req, verdict)

    if verdict.decision is Decision.BLOCK:
        return {
            "request_id": req.request_id,
            "decision": Decision.BLOCK.value,
            "reason": verdict.reason,
        }

    try:
        response = mcp_client.execute(req.request_id, req.tool, req.arguments)
    except McpUnavailableError as exc:
        logger.error("MCP unavailable for %s: %s", req.request_id, exc)
        audit.mark_execution(db, req.request_id, ExecutionStatus.FAILED)
        raise ExecutionFailedError(
            f"MCP execution failed: MCP unavailable (request {req.request_id})."
        ) from exc

    if response.status_code != 200:
        detail = str(response.body.get("detail", ""))[:200]
        logger.error("MCP returned HTTP %s for %s: %s", response.status_code, req.request_id, detail)
        audit.mark_execution(db, req.request_id, ExecutionStatus.FAILED)
        raise ExecutionFailedError(
            f"MCP execution failed (HTTP {response.status_code}): {detail}"
        )

    audit.mark_execution(db, req.request_id, ExecutionStatus.EXECUTED)
    return {
        "request_id": req.request_id,
        "decision": Decision.ALLOW.value,
        "result": response.body.get("result"),
    }