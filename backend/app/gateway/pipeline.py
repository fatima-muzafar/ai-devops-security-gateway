"""
Gateway pipeline orchestrator (Section 8; decisions.md #31, #34, #35, #38, #41, #51, #52).

evaluate() is READ-ONLY and short-circuits on the first failing stage:
authentication + agent identification -> tool registry -> arguments -> service ->
ownership -> policy. handle_tool_request() then writes the single audit row
(committed BEFORE any MCP call) and, on ALLOW only, calls MCP over HTTP and records
the outcome.

Phase 9: after every Step 1 stage passes, evaluate() computes rule risk (gateway/risk.py,
decisions.md #53-#59, #62; read-only) and the Verdict carries it; the audit module writes
it with the audit row in ONE commit (#58).

Phase 11 (#78-#80, #89): the decision is now ENFORCED. decide_from_risk() maps the final risk
and the policy approval flag (Section 11 Step 4): LOW -> ALLOW, otherwise APPROVAL_REQUIRED.
APPROVAL_REQUIRED writes the audit, risk and approval rows in ONE commit and a `pending`
behavior event, and never calls MCP. Approval and execution live in app/approvals/.

Phase 10: after the final outcome (and after the audit commit) a behavior_events row is written
by gateway/behavior_log.py in its OWN commit, fail-open (decisions.md #69, #70).

Not here (still deferred): ML.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.database.enums import Decision, Environment, EventOutcome, ExecutionStatus
from app.database.models import Service
from app.gateway import audit
from app.gateway.behavior_log import record_behavior_event
from app.gateway.identity import resolve_identity
from app.gateway.mcp_client import McpUnavailableError
from app.gateway.ownership import check_ownership
from app.gateway.decision import APPROVAL_REASON, decide_from_risk
from app.gateway.policy import evaluate_policy
from app.gateway.revalidation import take_snapshot
from app.gateway.risk import RiskEvaluation, assess_risk
from app.gateway.validation import check_arguments, check_tool_registry, resolve_service

logger = logging.getLogger(__name__)


class ExecutionFailedError(Exception):
    """ALLOWED request whose MCP execution failed. Mapped to HTTP 502 (#34)."""


@dataclass(frozen=True)
class GatewayRequest:
    request_id: str
    user_id: str  # a CLAIM; must equal the token subject (#44)
    agent_id: str | None
    tool: str
    arguments: dict[str, Any]
    raw_request: dict[str, Any]
    token: str | None = field(default=None, repr=False)  # never stored or logged (#51)


@dataclass
class Verdict:
    decision: Decision
    reason: str | None = None
    user_id: int | None = None
    agent_id: int | None = None
    tool_id: int | None = None
    service_id: int | None = None
    environment: Environment | None = None
    risk: RiskEvaluation | None = None  # set only for requests that passed every Step 1 stage
    requires_approval: bool = False  # the policy flag (#78)
    state_snapshot: dict | None = None  # set only when APPROVAL_REQUIRED (#80, #81)


def evaluate(db: Session, req: GatewayRequest) -> Verdict:
    ident = resolve_identity(db, req.token, req.user_id, req.agent_id)
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

    # Identity passed, so ident.user is set. The role is read from the DB row (#44).
    ownership_reason = check_ownership(
        db, ident.user, service.service_id, args.service_name, args.environment
    )
    if ownership_reason:
        return Verdict(Decision.BLOCK, ownership_reason, **resolved)

    policy = evaluate_policy(db, ident.user.role, req.tool, args.environment)
    if policy.block_reason:
        return Verdict(Decision.BLOCK, policy.block_reason, **resolved)

    # Every Step 1 stage passed: compute risk (read-only), then map it to a decision (#78).
    risk = assess_risk(
        db,
        user_id=ident.user.id,
        tool_name=req.tool,
        sensitivity=tool.sensitivity,
        environment=args.environment,
        service_id=service.service_id,
        requires_approval=policy.requires_approval,
    )
    decision = decide_from_risk(risk.final_risk_level, policy.requires_approval)
    if decision is Decision.APPROVAL_REQUIRED:
        snapshot = take_snapshot(db.get(Service, service.service_id))
        return Verdict(
            decision, APPROVAL_REASON, risk=risk, requires_approval=policy.requires_approval,
            state_snapshot=snapshot, **resolved,
        )
    return Verdict(decision, None, risk=risk, requires_approval=policy.requires_approval, **resolved)


def handle_tool_request(db: Session, mcp_client, req: GatewayRequest) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)  # #70: the event timestamp, captured at pipeline start
    verdict = evaluate(db, req)

    # One audit INSERT, committed BEFORE any MCP call (#35). A duplicate
    # request_id raises DuplicateRequestError here, before MCP is reachable.
    audit.record_decision(db, req, verdict)

    if verdict.decision is Decision.BLOCK:
        record_behavior_event(
            db, verdict, request_id=req.request_id, timestamp=started_at, outcome=EventOutcome.BLOCKED
        )
        return {
            "request_id": req.request_id,
            "decision": Decision.BLOCK.value,
            "reason": verdict.reason,
        }

    if verdict.decision is Decision.APPROVAL_REQUIRED:
        # #80: audit + risk + approval rows are already committed; no MCP call. The event is
        # `pending` and is resolved later by the approvals router (#85).
        record_behavior_event(
            db, verdict, request_id=req.request_id, timestamp=started_at, outcome=EventOutcome.PENDING
        )
        return {
            "request_id": req.request_id,
            "decision": Decision.APPROVAL_REQUIRED.value,
            "reason": verdict.reason,
        }

    try:
        response = mcp_client.execute(req.request_id, req.tool, req.arguments)
    except McpUnavailableError as exc:
        logger.error("MCP unavailable for %s: %s", req.request_id, exc)
        audit.mark_execution(db, req.request_id, ExecutionStatus.FAILED)
        record_behavior_event(
            db, verdict, request_id=req.request_id, timestamp=started_at, outcome=EventOutcome.FAILED
        )
        raise ExecutionFailedError(
            f"MCP execution failed: MCP unavailable (request {req.request_id})."
        ) from exc

    if response.status_code != 200:
        detail = str(response.body.get("detail", ""))[:200]
        logger.error("MCP returned HTTP %s for %s: %s", response.status_code, req.request_id, detail)
        audit.mark_execution(db, req.request_id, ExecutionStatus.FAILED)
        record_behavior_event(
            db, verdict, request_id=req.request_id, timestamp=started_at, outcome=EventOutcome.FAILED
        )
        raise ExecutionFailedError(
            f"MCP execution failed (HTTP {response.status_code}): {detail}"
        )

    audit.mark_execution(db, req.request_id, ExecutionStatus.EXECUTED)
    result = response.body.get("result")
    record_behavior_event(
        db,
        verdict,
        request_id=req.request_id,
        timestamp=started_at,
        outcome=EventOutcome.ALLOWED,
        result=result,
    )
    return {
        "request_id": req.request_id,
        "decision": Decision.ALLOW.value,
        "result": result,
    }