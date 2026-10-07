"""
Authentication + agent identification stage (decisions.md #42, #44, #45, #51).

REPLACES the Phase 7 username lookup. The caller proves who they are with a bearer
JWT; the `user_id` in the request body is only a CLAIM and must equal the token
subject. Role/ownership/policy are NOT decided here (Stage 3).

Audit FKs: auth failures record no user. A valid token with a mismatched claim
records the AUTHENTICATED user (agent stays NULL, agent stage not reached).
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.database.models import Agent, User
from app.gateway.auth import (
    AuthNotConfiguredError,
    TokenExpiredError,
    TokenInvalidError,
    verify_token,
)

_AUTH = "Authentication stage: "


@dataclass(frozen=True)
class IdentityResult:
    user: User | None
    agent_id: int | None
    block_reason: str | None

    @property
    def user_id(self) -> int | None:
        return self.user.id if self.user is not None else None


def resolve_identity(
    db: Session, token: str | None, claimed_user_id: str, agent_name: str | None
) -> IdentityResult:
    if not token:
        return IdentityResult(None, None, f"{_AUTH}missing bearer token.")

    try:
        subject = verify_token(token)
    except AuthNotConfiguredError:
        return IdentityResult(None, None, f"{_AUTH}authentication is not configured.")
    except TokenExpiredError:
        return IdentityResult(None, None, f"{_AUTH}token expired.")
    except TokenInvalidError:
        return IdentityResult(None, None, f"{_AUTH}invalid token.")

    user = db.query(User).filter_by(username=subject).one_or_none()
    if user is None:
        return IdentityResult(None, None, f"{_AUTH}token subject is not a known user.")

    if claimed_user_id != user.username:
        return IdentityResult(
            user, None, f"{_AUTH}request user_id does not match the authenticated user."
        )

    if not agent_name:
        return IdentityResult(user, None, "Identity stage: agent_id is required.")

    # agents.agent_name has no UNIQUE constraint (#33): deterministic first match.
    agent = db.query(Agent).filter_by(agent_name=agent_name).order_by(Agent.id).first()
    if agent is None:
        return IdentityResult(user, None, "Identity stage: unknown agent.")
    if agent.status != "active":
        return IdentityResult(user, agent.id, "Identity stage: agent is not active.")

    return IdentityResult(user, agent.id, None)