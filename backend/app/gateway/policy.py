"""
Policy stage (Section 9/11 Step 1; decisions.md #3, #46, #48, #50, #52).

REPLACES the Phase 5 placeholder. Role x tool x environment lookup in `policies`
(no service_id: ownership is a separate stage). Default-deny: only allowed=True rows
count and no matching row means BLOCK. The role is the one read from the users row.

A matching row with requires_approval set is a fail-closed BLOCK until Phase 11 turns
it into APPROVAL_REQUIRED (#48). If several allowed rows match and any requires
approval, the approval-bound BLOCK wins.
"""
from sqlalchemy.orm import Session

from app.database.enums import Environment, Role
from app.database.models import Policy, Tool
from app.gateway.validation import _q


def check_policy(db: Session, role: Role, tool_name: str, environment: Environment) -> str | None:
    """Return a BLOCK reason, or None when the action is permitted without approval."""
    rows = (
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
    if not rows:
        return (
            f"Policy stage: role '{role.value}' is not permitted to use "
            f"{_q(tool_name)} in '{environment.value}'."
        )
    if any(row.requires_approval for row in rows):
        return (
            f"Policy stage: {_q(tool_name)} in '{environment.value}' requires human approval; "
            "the approval workflow is not implemented yet (Phase 11). Request blocked."
        )
    return None