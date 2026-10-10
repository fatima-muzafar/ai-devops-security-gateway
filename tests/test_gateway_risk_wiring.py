"""
Phase 9 Stage 2: risk wired into the pipeline and persisted (decisions.md #58, #59, #60).

Drives the REAL Gateway. Risk is RECORDED, NOT ENFORCED until Phase 11: the decision is
ALLOW for any final level. Request ids start with QA-W-.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.database.base import SessionLocal
from app.database.enums import Decision, Environment, ExecutionStatus, RiskLevel, Role
from app.database.models import RiskAssessment, SecurityRequest, Service, ServiceStateHistory
from app.gateway import audit
from app.gateway.auth import issue_token
from app.gateway.mcp_client import McpResponse, get_mcp_client
from app.gateway.pipeline import GatewayRequest, evaluate
from app.gateway.risk import (
    COND_REPEATED_DENIALS,
    COND_S2,
    MARKER_INTERIM_NOT_ENFORCED,
    MARKER_ML_STUB,
)
from app.main import app
from qa_cleanup import delete_requests

PATH = "/api/gateway/tool-request"
ADMIN, JUNIOR = "qa_rw_admin", "qa_rw_junior"
SVC, OTHER_SVC = "qa-rw-svc", "qa-rw-junior-svc"
STAGING, PRODUCTION = Environment.STAGING, Environment.PRODUCTION
LOW, MEDIUM, HIGH = RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH


class World:
    def __init__(self, db, headers):
        self.db, self._headers = db, headers
        self.client = TestClient(app)

    def post(self, tool, svc=SVC, env="staging", who=ADMIN, tag="x", extra=None, rid=None,
             headers="auto", user_id=None, client=None, arguments=None):
        rid = rid or ("QA-W-" + tag + uuid.uuid4().hex)[:32]
        args = arguments if arguments is not None else {
            "service_name": svc, "environment": env, **(extra or {})}
        body = {"request_id": rid, "user_id": user_id or who, "agent_id": "AG001",
                "tool": tool, "arguments": args}
        hdr = self._headers(who) if headers == "auto" else headers
        resp = (client or self.client).post(PATH, json=body, headers=hdr)
        return rid, resp

    def request_row(self, rid):
        self.db.rollback()
        return self.db.get(SecurityRequest, rid)

    def risk_rows(self, rid):
        self.db.rollback()
        return self.db.query(RiskAssessment).filter_by(request_id=rid).all()

    def risk(self, rid):
        rows = self.risk_rows(rid)
        assert len(rows) == 1, f"expected exactly one risk row, got {len(rows)}"
        return rows[0]


@pytest.fixture
def w(db, make_user, ag001_agent, auth_headers):
    admin = make_user(ADMIN, Role.ADMIN)
    junior = make_user(JUNIOR, Role.JUNIOR_DEVELOPER)
    made = [
        Service(service_name=SVC, environment=STAGING, current_version=1, known_good_version=1,
                owner_id=admin.id, status="healthy"),
        Service(service_name=SVC, environment=PRODUCTION, current_version=1, known_good_version=1,
                owner_id=admin.id, status="healthy"),
        Service(service_name=OTHER_SVC, environment=STAGING, current_version=1,
                known_good_version=1, owner_id=junior.id, status="healthy"),
    ]
    db.add_all(made)
    db.commit()
    ids = [s.id for s in made]
    yield World(db, auth_headers)
    db.rollback()
    delete_requests(db, SecurityRequest.service_id.in_(ids))
    db.query(ServiceStateHistory).filter(ServiceStateHistory.service_id.in_(ids)).delete(
        synchronize_session=False)
    db.query(Service).filter(Service.id.in_(ids)).delete(synchronize_session=False)
    db.commit()


class FakeMcp:
    """Counts calls; optionally records what the DB looked like AT the moment MCP is called."""

    def __init__(self, status=200):
        self.status, self.calls, self.seen_at_call = status, 0, None

    def execute(self, request_id, tool, arguments):
        self.calls += 1
        session = SessionLocal()  # separate connection: sees only COMMITTED data
        try:
            self.seen_at_call = (
                session.query(SecurityRequest).filter_by(request_id=request_id).count(),
                session.query(RiskAssessment).filter_by(request_id=request_id).count(),
            )
        finally:
            session.close()
        if self.status == 200:
            return McpResponse(200, {"result": {"ok": True}})
        return McpResponse(self.status, {"detail": "boom"})


# --------------------------------------------------------------------------- ALLOW rows


def test_allowed_read_writes_one_low_risk_row(w):
    rid, resp = w.post("get_logs")
    assert resp.status_code == 200 and resp.json()["decision"] == "ALLOW"
    r = w.risk(rid)
    assert (r.rule_risk_level, r.ml_risk_level, r.final_risk_level) == (LOW, LOW, LOW)
    assert r.decision is Decision.ALLOW and r.is_production is False
    assert r.reasons == [MARKER_ML_STUB]
    assert w.request_row(rid).execution_status is ExecutionStatus.EXECUTED


def test_owned_staging_restart_is_low_without_the_interim_marker(w):
    rid, resp = w.post("restart_service")
    assert resp.json()["decision"] == "ALLOW"
    r = w.risk(rid)
    assert r.final_risk_level is LOW
    assert MARKER_INTERIM_NOT_ENFORCED not in r.reasons


def test_production_restart_is_medium_recorded_but_still_allowed(w):
    rid, resp = w.post("restart_service", env="production")
    assert resp.status_code == 200 and resp.json()["decision"] == "ALLOW"  # NOT enforced yet
    r = w.risk(rid)
    assert (r.rule_risk_level, r.final_risk_level) == (MEDIUM, MEDIUM)
    assert r.decision is Decision.ALLOW and r.is_production is True
    assert r.reasons == ["production_targeting:medium", MARKER_ML_STUB, MARKER_INTERIM_NOT_ENFORCED]
    assert w.request_row(rid).execution_status is ExecutionStatus.EXECUTED


def test_production_rollback_is_high_because_the_registry_sensitivity_reaches_the_engine(w):
    app.dependency_overrides[get_mcp_client] = lambda: FakeMcp()  # mock rollback semantics not under test
    rid, resp = w.post("rollback_deployment", env="production")
    assert resp.json()["decision"] == "ALLOW"
    r = w.risk(rid)
    assert (r.rule_risk_level, r.final_risk_level) == (HIGH, HIGH)
    assert r.reasons[0] == "production_targeting:high"


def test_s2_burst_is_high_end_to_end_and_still_allowed(w):
    for i in range(3):  # admin is not the owner of the junior's service: Ownership BLOCKs
        _, blocked = w.post("get_logs", svc=OTHER_SVC, tag=f"d{i}")
        assert blocked.json()["decision"] == "BLOCK"
    rid, resp = w.post("restart_service")
    assert resp.json()["decision"] == "ALLOW"
    r = w.risk(rid)
    assert r.final_risk_level is HIGH
    assert COND_S2 in r.reasons and COND_REPEATED_DENIALS in r.reasons
    assert r.reasons[-1] == MARKER_INTERIM_NOT_ENFORCED


# --------------------------------------------------------------------------- BLOCK: no risk row


@pytest.mark.parametrize(
    "case",
    ["tool", "arguments", "service", "auth", "ownership", "policy", "approval_bound"],
)
def test_no_risk_row_for_any_block(w, case):
    if case == "tool":
        rid, resp = w.post("no_such_tool")
    elif case == "arguments":
        rid, resp = w.post("get_logs", arguments={})
    elif case == "service":
        rid, resp = w.post("get_logs", svc="qa-rw-missing")
    elif case == "auth":
        rid, resp = w.post("get_logs", headers={})
    elif case == "ownership":
        rid, resp = w.post("get_logs", svc=OTHER_SVC)
    elif case == "policy":  # junior owns it but may not deploy
        rid, resp = w.post("deploy_service", svc=OTHER_SVC, who=JUNIOR, extra={"target_version": 2})
    else:  # #48: approval-bound production deploy stops at Policy, before risk
        rid, resp = w.post("deploy_service", env="production", extra={"target_version": 2})
        assert "requires human approval" in resp.json()["reason"]
    assert resp.status_code == 200 and resp.json()["decision"] == "BLOCK"
    assert w.request_row(rid).decision is Decision.BLOCK  # audit row still written
    assert w.risk_rows(rid) == []


# --------------------------------------------------------------------------- contract (#60)


def test_response_key_sets_are_unchanged(w):
    _, ok = w.post("get_logs")
    _, blocked = w.post("get_logs", svc=OTHER_SVC)
    assert set(ok.json()) == {"request_id", "decision", "result"}
    assert set(blocked.json()) == {"request_id", "decision", "reason"}


# --------------------------------------------------------------------------- write order (#58)


def test_audit_and_risk_rows_are_committed_before_mcp_is_called(w):
    fake = FakeMcp()
    app.dependency_overrides[get_mcp_client] = lambda: fake
    rid, resp = w.post("restart_service")
    assert resp.status_code == 200 and fake.calls == 1
    assert fake.seen_at_call == (1, 1)  # both rows visible to another connection at call time


def test_mcp_failure_keeps_the_risk_row_and_marks_the_request_failed(w):
    fake = FakeMcp(status=500)
    app.dependency_overrides[get_mcp_client] = lambda: fake
    rid, resp = w.post("restart_service")
    assert resp.status_code == 502
    assert w.request_row(rid).execution_status is ExecutionStatus.FAILED
    assert w.risk(rid).decision is Decision.ALLOW


def test_failed_risk_write_rolls_back_the_audit_row_and_never_calls_mcp(w, monkeypatch):
    fake = FakeMcp()
    app.dependency_overrides[get_mcp_client] = lambda: fake
    real = audit._build_risk_row

    def broken(req, verdict):
        row = real(req, verdict)
        row.reasons = [object()]  # not JSON-serialisable: fails at flush, AFTER the audit INSERT
        return row

    monkeypatch.setattr(audit, "_build_risk_row", broken)
    quiet = TestClient(app, raise_server_exceptions=False)
    rid, resp = w.post("restart_service", client=quiet)
    assert resp.status_code == 500
    assert fake.calls == 0
    assert w.request_row(rid) is None  # #58: no trace of the request (accepted limitation)
    assert w.risk_rows(rid) == []


def test_duplicate_request_id_is_409_with_one_audit_row_and_one_risk_row(w):
    rid, first = w.post("get_logs")
    original_risk_id = w.risk(rid).id
    _, second = w.post("get_logs", rid=rid)
    assert first.status_code == 200 and second.status_code == 409
    assert w.db.query(SecurityRequest).filter_by(request_id=rid).count() == 1
    assert w.risk(rid).id == original_risk_id  # untouched, not replaced


# --------------------------------------------------------------------------- evaluate() stays read-only


def test_evaluate_is_read_only_and_carries_risk_only_for_allow(w, db):
    token, _ = issue_token(ADMIN)

    def verdict(tool, svc):
        req = GatewayRequest(
            request_id="QA-W-eval" + uuid.uuid4().hex[:10], user_id=ADMIN, agent_id="AG001",
            tool=tool, arguments={"service_name": svc, "environment": "staging"}, raw_request={},
            token=token)
        return evaluate(db, req)

    before = (db.query(SecurityRequest).count(), db.query(RiskAssessment).count())
    allowed = verdict("restart_service", SVC)
    blocked = verdict("get_logs", OTHER_SVC)
    assert (db.query(SecurityRequest).count(), db.query(RiskAssessment).count()) == before
    assert allowed.decision is Decision.ALLOW and allowed.risk.final_risk_level is LOW
    assert blocked.decision is Decision.BLOCK and blocked.risk is None
