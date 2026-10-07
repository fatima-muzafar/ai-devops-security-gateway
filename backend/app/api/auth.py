"""
POST /api/auth/login (decisions.md #42). Not in Section 17; added because FR-01
needs real authentication.

Failures are generic: one 401 body for unknown user and wrong password. A
misconfigured JWT_SECRET is a 503 (fail closed), checked BEFORE credentials.
Login attempts are not audited in security_requests (keyed by tool request_id).
Sync `def`, like every route in this app (#26).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.gateway.auth import (
    AuthNotConfiguredError,
    authenticate_user,
    issue_token,
    require_secret,
)

router = APIRouter()


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=1024)


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/api/auth/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    try:
        require_secret()
        user = authenticate_user(db, payload.username, payload.password)
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid username or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token, expires_in = issue_token(user.username)
    except AuthNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail="Authentication is not configured.") from exc

    return LoginOut(access_token=token, expires_in=expires_in)