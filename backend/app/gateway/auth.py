"""
Authentication primitives (decisions.md #42, #43): password hashing and JWTs.

Proves WHO is calling; makes no authorization decision. Used by api/auth.py
(login) in Stage 1; the Gateway and /api/chat verify tokens from Stage 2.

JWT_SECRET is read at REQUEST time, never cached (as #40). Unset, empty or
shorter than 32 characters fails closed. That also rejects the .env.example
value "changeme". No role claim: authorization always reads users.role from the DB.
"""
import os
import time
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy.orm import Session

from app.database.models import User

ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 60 * 60
MIN_SECRET_LENGTH = 32

_hasher = PasswordHasher()


class AuthNotConfiguredError(Exception):
    """JWT_SECRET is unset, empty, or shorter than MIN_SECRET_LENGTH."""


class TokenError(Exception):
    """Base class for token verification failures."""


class TokenInvalidError(TokenError):
    """Bad signature, wrong algorithm, malformed, or missing required claims."""


class TokenExpiredError(TokenError):
    """Signature valid but the token is past its `exp`."""


# ----------------------------------------------------------------- passwords
def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def is_argon2_hash(value: str) -> bool:
    return value.startswith("$argon2")


def verify_password(plain: str, hashed: str) -> bool:
    """False for a wrong password AND for any non-argon2 stored value (the
    Phase 3 placeholder, the unusable marker); never raises on bad hashes."""
    try:
        return _hasher.verify(hashed, plain)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return _hasher.hash("timing-equalizer")


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    """Return the user on a correct password, else None. Every failure path
    performs one argon2 verification so timing does not reveal which case it was."""
    user = db.query(User).filter_by(username=username).one_or_none()
    if user is None or not is_argon2_hash(user.hashed_password):
        verify_password(password, _dummy_hash())
        return None
    return user if verify_password(password, user.hashed_password) else None


# -------------------------------------------------------------------- tokens
def require_secret() -> str:
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < MIN_SECRET_LENGTH:
        raise AuthNotConfiguredError(
            f"JWT_SECRET must be set to at least {MIN_SECRET_LENGTH} characters."
        )
    return secret


def issue_token(username: str, ttl_seconds: int = TOKEN_TTL_SECONDS) -> tuple[str, int]:
    """Return (token, expires_in_seconds). ttl_seconds exists so tests can
    mint expired tokens."""
    secret = require_secret()
    now = int(time.time())
    claims = {"sub": username, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(claims, secret, algorithm=ALGORITHM), ttl_seconds


def verify_token(token: str) -> str:
    """Return the username (`sub`). Algorithm is pinned, so alg=none is rejected."""
    secret = require_secret()
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenInvalidError("invalid token") from exc

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise TokenInvalidError("invalid token subject")
    return subject