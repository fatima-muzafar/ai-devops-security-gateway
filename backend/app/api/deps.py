"""
Shared request dependencies (decisions.md #51): bearer-token extraction for the
Gateway and chat routes, and the authenticated caller for /api/chat.

The Gateway does NOT use require_caller: it verifies the token inside the pipeline
so auth failures become audited BLOCK decisions (#45).
"""
from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.database.models import User
from app.gateway.auth import AuthNotConfiguredError, TokenError, verify_token


def bearer_token(authorization: str | None) -> str | None:
    """Return the token from 'Bearer <token>', else None (any other scheme/empty)."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def get_bearer_token(authorization: str | None = Header(default=None)) -> str | None:
    return bearer_token(authorization)


@dataclass(frozen=True)
class Caller:
    username: str
    token: str = field(repr=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_caller(
    token: str | None = Depends(get_bearer_token),
    db: Session = Depends(get_db),
) -> Caller:
    if not token:
        raise _unauthorized()
    try:
        username = verify_token(token)
    except AuthNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail="Authentication is not configured.") from exc
    except TokenError as exc:
        raise _unauthorized() from exc

    user = db.query(User).filter_by(username=username).one_or_none()
    db.rollback()  # end the read transaction: the agent turn can take seconds
    if user is None:
        raise _unauthorized()
    return Caller(username=username, token=token)