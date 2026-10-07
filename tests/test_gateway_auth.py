"""
Phase 8 Stage 2: the Authentication stage at the Gateway (decisions.md #44, #45, #51).

Auth failures are audited BLOCK decisions (HTTP 200), never HTTP 401. The token is
never stored. A valid token with a mismatched `user_id` claim records the
AUTHENTICATED user in the audit FK. request_ids start with QA-S2- (purged by prefix).
"""
import json
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.database.base import SessionLocal
from app.database.enums import Decision, ExecutionStatus
from app.database.models import SecurityRequest, User
from app.gateway.auth import issue_token
from app.gateway.mcp_client import get_mcp_client
from app.main import app

client = TestClient(app)
PATH = "/api/gateway/tool-request"
USER = "qa_test_owner"
SERVICE = "qa-test-service"
AUTH = "Authentication stage: "
MISMATCH = AUTH + "request user_id does not match the authenticated user."


@pytest.fixture(autouse=True)
def purge_qa_s2_rows():
    def purge():
        session = SessionLocal()
        try:
            session.query(SecurityRequest).filter(
                SecurityRequest.request_id.like("QA-S2-%")
            ).delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()

    purge()
    yield
    purge()


class StubMcp:
    def __init__(self):
        self.calls = []

    def execute(self, request_id, tool, arguments):
        self.calls.append(request_id)
        raise AssertionError("MCP must not be reached")


def _no_mcp():
    stub = StubMcp()
    app.dependency_overrides[get_mcp_client] = lambda: stub  # conftest removes it
    return stub


def _payload(rid, **overrides):
    payload = {
        "request_id": rid,
        "user_id": USER,
        "agent_id": "AG001",
        "tool": "restart_service",
        "arguments": {"service_name": SERVICE, "environment": "staging"},
    }
    payload.update(overrides)
    return payload


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _token(user=USER):
    return issue_token(user)[0]


def _row(db, rid):
    db.expire_all()
    return db.get(SecurityRequest, rid)


def _build(kind):
    now = int(time.time())
    claims = {"sub": USER, "iat": now, "exp": now + 60}
    if kind == "missing":
        return {}, "missing bearer token."
    if kind == "wrong-scheme":
        return {"Authorization": f"Basic {_token()}"}, "missing bearer token."
    if kind == "garbage":
        return _bearer("not.a.jwt"), "invalid token."
    if kind == "expired":
        return _bearer(issue_token(USER, ttl_seconds=-10)[0]), "token expired."
    if kind == "wrong-secret":
        return _bearer(jwt.encode(claims, "x" * 40, algorithm="HS256")), "invalid token."
    if kind == "alg-none":
        return _bearer(jwt.encode(claims, None, algorithm="none")), "invalid token."
    if kind == "unknown-subject":
        return _bearer(_token("qa_no_such_user")), "token subject is not a known user."
    raise AssertionError(kind)


@pytest.mark.parametrize(
    "kind",
    ["missing", "wrong-scheme", "garbage", "expired", "wrong-secret", "alg-none", "unknown-subject"],
)
def test_authentication_failure_is_an_audited_block_with_no_fks(db, test_service, kind):
    stub = _no_mcp()
    headers, fragment = _build(kind)
    payload = _payload(f"QA-S2-AUTH-{kind}")

    res = client.post(PATH, json=payload, headers=headers)

    assert res.status_code == 200  # a BLOCK decision, not an HTTP 401 (#45)
    body = res.json()
    assert set(body) == {"request_id", "decision", "reason"}
    assert body["decision"] == "BLOCK"
    assert body["reason"] == AUTH + fragment
    assert stub.calls == []

    row = _row(db, payload["request_id"])
    assert row.decision == Decision.BLOCK
    assert row.reason == body["reason"]
    assert row.execution_status == ExecutionStatus.NOT_EXECUTED
    assert row.user_id is None and row.agent_id is None
    assert row.tool_id is None and row.service_id is None and row.environment is None
    assert row.raw_request == payload


def test_unconfigured_secret_is_an_audited_block(db, test_service, monkeypatch):
    stub = _no_mcp()
    token = _token()  # minted while the secret was valid
    monkeypatch.setenv("JWT_SECRET", "changeme")

    res = client.post(PATH, json=_payload("QA-S2-NOCONF"), headers=_bearer(token))

    assert res.status_code == 200
    assert res.json()["reason"] == AUTH + "authentication is not configured."
    assert stub.calls == []
    assert _row(db, "QA-S2-NOCONF").user_id is None


def test_authentication_precedes_every_other_stage(db, test_service):
    stub = _no_mcp()

    res = client.post(
        PATH,
        json=_payload("QA-S2-FIRST", tool="delete_everything", agent_id="QA-NO-SUCH-AGENT"),
        headers=_bearer("not.a.jwt"),
    )

    assert res.json()["reason"] == AUTH + "invalid token."
    assert stub.calls == []


# ------------------------------------------------- claim vs token (#44, #51)
def test_valid_token_with_mismatched_claim_records_the_authenticated_user(db, test_service, make_user):
    other = make_user("qa_other")
    stub = _no_mcp()
    payload = _payload("QA-S2-MM-1", user_id="qa_other")  # claims qa_other...

    res = client.post(PATH, json=payload, headers=_bearer(_token(USER)))  # ...holds USER's token

    assert res.status_code == 200
    assert res.json()["reason"] == MISMATCH
    assert stub.calls == []
    row = _row(db, "QA-S2-MM-1")
    owner_id = db.query(User).filter_by(username=USER).one().id
    assert row.user_id == owner_id  # the AUTHENTICATED user, not the claimed one
    assert row.user_id != other.id
    assert row.agent_id is None
    assert row.raw_request["user_id"] == "qa_other"  # the claim is preserved as evidence


def test_impersonating_the_service_owner_with_anothers_token_is_blocked(db, test_service, make_user):
    other = make_user("qa_other")
    stub = _no_mcp()
    payload = _payload("QA-S2-MM-2")  # claims the owner...

    res = client.post(PATH, json=payload, headers=_bearer(_token("qa_other")))  # ...token of qa_other

    assert res.json()["reason"] == MISMATCH
    assert stub.calls == []
    assert _row(db, "QA-S2-MM-2").user_id == other.id


def test_acting_identity_is_the_token_subject_and_the_token_is_not_stored(db, test_service, make_user):
    other = make_user("qa_other")
    token = _token("qa_other")
    payload = _payload("QA-S2-ID-1", user_id="qa_other")

    res = client.post(PATH, json=payload, headers=_bearer(token))

    # Stage 2 keeps the placeholder policy, so any authenticated user may act on
    # staging; Stage 3 adds ownership and role policy.
    assert res.status_code == 200
    assert res.json()["decision"] == "ALLOW"
    row = _row(db, "QA-S2-ID-1")
    assert row.user_id == other.id
    assert row.agent_id is not None
    assert row.execution_status == ExecutionStatus.EXECUTED
    assert token not in json.dumps(row.raw_request)
    assert token not in (row.reason or "")
    assert "authorization" not in {k.lower() for k in row.raw_request}