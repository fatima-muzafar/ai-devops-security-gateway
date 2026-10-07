"""
Ownership stage (decisions.md #3, #47, #52). Separate from policy: "who is assigned to
this service row" is decided here, "what may this role do" in policy.py.

Assigned = services.owner_id == the AUTHENTICATED user's id for the specific
(service_name, environment) row. Applies to all five tools, reads included
(Section 9 clarification). Admin does NOT bypass (Section 9: "any role + unassigned
service -> BLOCK"). The reason never names the owner.
"""
from sqlalchemy.orm import Session

from app.database.enums import Environment
from app.database.models import Service, User
from app.gateway.validation import _q


def check_ownership(
    db: Session,
    user: User,
    service_id: int,
    service_name: str,
    environment: Environment,
) -> str | None:
    """Return a BLOCK reason, or None when the user owns the row."""
    service = db.get(Service, service_id)  # already in the identity map: no extra query
    if service is None or service.owner_id != user.id:
        return (
            f"Ownership stage: user {_q(user.username)} is not assigned to "
            f"{_q(service_name)} in '{environment.value}'."
        )
    return None