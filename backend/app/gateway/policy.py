"""
Policy stage (Section 9/11 Step 1; decisions.md #3, #46, #48, #50, #52).

REPLACES the Phase 5 placeholder. Role x tool x environment lookup in `policies`
(no service_id: ownership is a separate stage). Default-deny: only allowed=True rows
count and no matching row means BLOCK. The role is the one read from the users row.

A matching row with requires_approval set is a fail-closed BLOCK until Phase 11 turns
it into APPROVAL_REQUIRED (#48). If several allowed rows match and any requires
approval, the approval-bound BLOCK wins.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.database.enums import Environment, Role
from app.database.models import Policy, Tool
from app.gateway.validation import _q


@dataclass(frozen=True)
class PolicyResult:
    """#78: block_reason is set only when the action is NOT permitted. requires_approval is
    meaningful only when it is permitted (an approval-bound permit row, #46/#50)."""
    block_reason: str | None
    requires_approval: bool = False


def _permit_rows(db: Session, role: Role, tool_name: str, environment: Environment) -> list[Policy]:
    return (
        db.query(Policy)
        .join(Tool, Policy.tool_id == Tool.id)
        .filter(
            Tool.tool_name == tool_name,
            Policy.role == role,
            Policy.environment == environment,
            Policy.allowed.is_(True),
        )
        .all()
    )


def _not_permitted(role: Role, tool_name: str, environment: Environment) -> str:
    return (
        f"Policy stage: role '{role.value}' is not permitted to use "
        f"{_q(tool_name)} in '{environment.value}'."
    )


def evaluate_policy(
    db: Session, role: Role, tool_name: str, environment: Environment
) -> PolicyResult:
    """Phase 11 (#78): permit / deny plus the approval flag. No matching allowed row = deny.
    If several allowed rows match and ANY requires approval, requires_approval is True
    (fail closed)."""
    rows = _permit_rows(db, role, tool_name, environment)
    if not rows:
        return PolicyResult(_not_permitted(role, tool_name, environment), False)
    return PolicyResult(None, any(row.requires_approval for row in rows))


def check_policy(db: Session, role: Role, tool_name: str, environment: Environment) -> str | None:
    """Return a BLOCK reason, or None when the action is permitted without approval.
    Phase 8 behaviour, kept until Stage 2 of Phase 11 switches the pipeline to
    evaluate_policy() (#78)."""
    rows = _permit_rows(db, role, tool_name, environment)
    if not rows:
        return _not_permitted(role, tool_name, environment)
    if any(row.requires_approval for row in rows):
        return (
            f"Policy stage: {_q(tool_name)} in '{environment.value}' requires human approval; "
            "the approval workflow is not implemented yet (Phase 11). Request blocked."
        )
    return None
