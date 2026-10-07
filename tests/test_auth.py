"""
Phase 8 Stage 1: password hashing, JWT issue/verify, secret handling and
POST /api/auth/login (decisions.md #42, #43). Passwords are random per test.
"""
import os
import secrets
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.database.enums import Role
from app.database.models import User
from app.gateway.auth import (
    TOKEN_TTL_SECONDS,
    AuthNotConfiguredError,
    TokenExpiredError,
    TokenInvalidError,
    hash_password,
    issue_token,
    verify_password,
    verify_token,
)
from app.main import app

client = TestClient(app)
LOGIN = "/api/auth/login"
QA_USER = "qa_auth_user"


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", secrets.token_hex(32))


@pytest.fixture
def login_user(db):
    password = secrets.token_urlsafe(16)
    db.query(User).filter_by(username=QA_USER).delete()
    db.add(User(username=QA_USER, hashed_password=hash_password(password), role=Role.JUNIOR_DEVELOPER))
    db.commit()
    yield QA_USER, password
    db.rollback()
    db.query(User).filter_by(username=QA_USER).delete()
    db.commit()


# ----------------------------------------------------------------- passwords
def test_hash_and_verify_password():
    pw = secrets.token_urlsafe(12)
    hashed = hash_password(pw)
    assert hashed.startswith("$argon2")
    assert hashed != hash_password(pw)  # salted
    assert verify_password(pw, hashed) is True
    assert verify_password(pw + "x", hashed) is False


@pytest.mark.parametrize("stored", ["!unusable", "phase8-not-yet-implemented", ""])
def test_non_argon2_stored_values_never_verify(stored):
    assert verify_password("anything", stored) is False


# -------------------------------------------------------------------- tokens
def test_token_round_trip():
    token, expires_in = issue_token("alice")
    assert expires_in == TOKEN_TTL_SECONDS == 3600
    assert verify_token(token) == "alice"


def test_expired_token_is_rejected_as_expired():
    token, _ = issue_token("alice", ttl_seconds=-10)
    with pytest.raises(TokenExpiredError):
        verify_token(token)


def test_token_signed_with_another_secret_is_invalid():
    now = int(time.time())
    forged = jwt.encode({"sub": "alice", "iat": now, "exp": now + 60}, "x" * 40, algorithm="HS256")
    with pytest.raises(TokenInvalidError):
        verify_token(forged)


def test_alg_none_token_is_rejected():
    now = int(time.time())
    unsigned = jwt.encode({"sub": "alice", "iat": now, "exp": now + 60}, None, algorithm="none")
    with pytest.raises(TokenInvalidError):
        verify_token(unsigned)


@pytest.mark.parametrize("missing", ["exp", "sub", "iat"])
def test_token_missing_a_required_claim_is_invalid(missing):
    now = int(time.time())
    claims = {"sub": "alice", "iat": now, "exp": now + 60}
    claims.pop(missing)
    token = jwt.encode(claims, os.environ["JWT_SECRET"], algorithm="HS256")
    with pytest.raises(TokenInvalidError):
        verify_token(token)


@pytest.mark.parametrize("garbage", ["", "not.a.jwt", "abc"])
def test_garbage_token_is_invalid(garbage):
    with pytest.raises(TokenInvalidError):
        verify_token(garbage)


@pytest.mark.parametrize("value", [None, "", "changeme", "x" * 31])
def test_unconfigured_or_weak_secret_fails_closed(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("JWT_SECRET", raising=False)
    else:
        monkeypatch.setenv("JWT_SECRET", value)
    with pytest.raises(AuthNotConfiguredError):
        issue_token("alice")
    with pytest.raises(AuthNotConfiguredError):
        verify_token("anything")


def test_secret_of_exactly_32_chars_is_accepted(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    assert verify_token(issue_token("alice")[0]) == "alice"


# --------------------------------------------------------------------- login
def test_login_success_returns_a_verifiable_token(login_user):
    username, password = login_user

    res = client.post(LOGIN, json={"username": username, "password": password})

    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"access_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert verify_token(body["access_token"]) == username


def test_login_failures_are_indistinguishable(login_user):
    username, _ = login_user

    wrong_pw = client.post(LOGIN, json={"username": username, "password": "qa-wrong-password"})
    no_user = client.post(LOGIN, json={"username": "qa_no_such_user", "password": "qa-wrong-password"})

    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_login_with_unusable_hash_is_401(db):
    db.query(User).filter_by(username=QA_USER).delete()
    db.add(User(username=QA_USER, hashed_password="!unusable", role=Role.JUNIOR_DEVELOPER))
    db.commit()
    try:
        res = client.post(LOGIN, json={"username": QA_USER, "password": "anything"})
        assert res.status_code == 401
    finally:
        db.rollback()
        db.query(User).filter_by(username=QA_USER).delete()
        db.commit()


def test_login_with_unconfigured_secret_is_503_even_with_valid_credentials(login_user, monkeypatch):
    username, password = login_user
    monkeypatch.setenv("JWT_SECRET", "changeme")

    res = client.post(LOGIN, json={"username": username, "password": password})

    assert res.status_code == 503
    assert res.json() == {"detail": "Authentication is not configured."}


@pytest.mark.parametrize("body", [{}, {"username": "x"}, {"password": "x"}, {"username": "", "password": "x"}])
def test_login_malformed_body_is_422(body):
    assert client.post(LOGIN, json=body).status_code == 422