"""
Identity LOOKUP stage (decisions.md #31, #41). NOT authentication: no password,
no JWT; anyone can still claim any username. Phase 8 replaces this.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.database.models import Agent, User


@dataclass(frozen=True)
class IdentityResult:
    user_id: int | None
    agent_id: int | None
    block_reason: str | None


def resolve_identity(db: Session, user_name: str, agent_name: str | None) -> IdentityResult:
    user = db.query(User).filter_by(username=user_name).one_or_none()
    if user is None:
        return IdentityResult(None, None, "Identity stage: unknown user.")

    if not agent_name:
        return IdentityResult(user.id, None, "Identity stage: agent_id is required.")

    # agents.agent_name has no UNIQUE constraint (#33): deterministic first match.
    agent = db.query(Agent).filter_by(agent_name=agent_name).order_by(Agent.id).first()
    if agent is None:
        return IdentityResult(user.id, None, "Identity stage: unknown agent.")
    if agent.status != "active":
        return IdentityResult(user.id, agent.id, "Identity stage: agent is not active.")

    return IdentityResult(user.id, agent.id, None)