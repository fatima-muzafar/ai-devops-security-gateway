"""
TOCTOU-style revalidation (Section 8/11/14; decisions.md #84). READ-ONLY.

Runs right before MCP for an APPROVED request. It re-checks, from the stored request:
requester + agent (DB lookup: the token is not stored, #44/#51), tool, arguments, service,
ownership, policy, and the service-version snapshot. Policy requires_approval=True counts as
SATISFIED here (the human already approved): this module never asks for approval again.
Risk is NOT recomputed. Any failure is a BLOCK reason, never an exception.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.database.enums import ApprovalStatus, ExecutionStatus
from app.database.models import (
    Agent, ApprovalRequest, SecurityRequest, Service, Tool, User,
)
from app.gateway.ownership import check_ownership
from app.gateway.policy import evaluate_policy
from app.gateway.validation import (
    _q, check_arguments, check_tool_registry, resolve_service,
)

SNAPSHOT_FIELDS = ("current_version", "known_good_version")
PASSED = "passed"


@dataclass(frozen=True)
class RevalidationResult:
    ok: bool
    reason: str | None = None

    @property
    def stored_text(self) -> str:
        """What goes into approval_requests.revalidation (#81)."""
        return PASSED if self.ok else (self.reason or "Revalidation stage: failed.")


def take_snapshot(service: Service) -> dict[str, int]:
    return {field: int(getattr(service, field)) for field in SNAPSHOT_FIELDS}


def _fail(reason: str) -> RevalidationResult:
    return RevalidationResult(False, f"Revalidation stage: {reason}")


def revalidate_approval(db: Session, approval: ApprovalRequest) -> RevalidationResult:
    if approval.status != ApprovalStatus.APPROVED:
        return _fail(f"approval is '{approval.status.value}', not 'approved'.")
    sec = db.get(SecurityRequest, approval.request_id)
    if sec is None:
        return _fail("the original request row is missing.")
    if sec.execution_status != ExecutionStatus.NOT_EXECUTED:
        return _fail(f"request already {sec.execution_status.value}.")

    user = db.get(User, sec.user_id) if sec.user_id is not None else None
    if user is None:
        return _fail("the requesting user no longer exists.")
    agent = db.get(Agent, sec.agent_id) if sec.agent_id is not None else None
    if agent is None or agent.status != "active":
        return _fail("the requesting agent is missing or not active.")
    tool = db.get(Tool, sec.tool_id) if sec.tool_id is not None else None
    if tool is None:
        return _fail("the requested tool row is missing.")

    tool_check = check_tool_registry(db, tool.tool_name)
    if tool_check.block_reason:
        return _fail(tool_check.block_reason)
    args_check = check_arguments(tool.tool_name, dict(sec.arguments or {}))
    if args_check.block_reason:
        return _fail(args_check.block_reason)
    service_check = resolve_service(db, args_check.service_name, args_check.environment)
    if service_check.block_reason:
        return _fail(service_check.block_reason)
    if service_check.service_id != sec.service_id:
        return _fail("the target service is no longer the one that was requested.")

    ownership = check_ownership(
        db, user, service_check.service_id, args_check.service_name, args_check.environment
    )
    if ownership:
        return _fail(ownership)
    policy = evaluate_policy(db, user.role, tool.tool_name, args_check.environment)
    if policy.block_reason:  # requires_approval is deliberately ignored (#84: no loop)
        return _fail(policy.block_reason)

    service = db.get(Service, service_check.service_id)
    snapshot = approval.state_snapshot or {}
    for field in SNAPSHOT_FIELDS:
        if field not in snapshot:
            return _fail(f"no stored snapshot value for {_q(field)}.")
        now_value = int(getattr(service, field))
        if now_value != snapshot[field]:
            return _fail(
                f"service state changed since the request was made "
                f"({field} {snapshot[field]} -> {now_value})."
            )
    return RevalidationResult(True)
