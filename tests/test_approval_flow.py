"""
Phase 11 Stage 2: the approval workflow end to end over HTTP (decisions.md #78-#89).

Real Gateway, real approvals router, and the REAL MCP seam (the autouse one) unless a test
swaps in a scripted MCP. Request ids start with QA-AF-. The fixture depends on make_user, so
it tears down (approvals, events, requests, history, services) before the users are deleted.
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.database.base import SessionLocal
from app.database.enums import (
    ApprovalStatus, ChangeType, Decision, Environment, EventOutcome, ExecutionStatus, Role,
)
from app.database.models import (
    ApprovalRequest, BehaviorEvent, Policy, RiskAssessment, SecurityRequest, Service,
    ServiceStateHistory, Tool, User,
)
from app.gateway import audit
from app.gateway.decision import APPROVAL_REASON
from app.gateway.mcp_client import McpResponse, McpUnavailableError, get_mcp_client
from app.gateway.risk import COND_REQUIRES_APPROVAL, COND_S1, MARKER_INTERIM_NOT_ENFORCED, MARKER_ML_STUB
from app.main import app
from qa_cleanup import delete_requests

TOOL_PATH = "/api/gateway/tool-request"
SENIOR, ADMIN, ADMIN2, JUNIOR = "qa_af_senior", "qa_af_admin", "qa_af_admin2", "qa_af_junior"
SVC, ADMIN_SVC = "qa-af-svc", "qa-af-admin-svc"
STAGING, PRODUCTION = Environment.STAGING, Environment.PRODUCTION
LIST_KEYS = {
    "id", "request_id", "status", "created_at", "decided_at", "reviewer", "reason",
    "revalidation", "requester", "agent", "service_name", "environment", "tool",
    "arguments", "risk",
}


class Scripted:
    """Scripted MCP: records every call; optionally fails."""

    def __init__(self, status=200, raises=False):
        self.status, self.raises, self.calls = status, raises, []

    def execute(self, request_id, tool, arguments):
        self.calls.append((request_id, tool, arguments))
        if self.raises:
            raise McpUnavailableError("down")
        if self.status == 200:
            return McpResponse(200, {"result": {"result": {"ok": True}}})
        return McpResponse(self.status, {"detail": "boom"})


def use_mcp(fake):
    app.dependency_overrides[get_mcp_client] = lambda: fake  # conftest removes it


class AF:
    def __init__(self, db, headers, ids):
        self.db, self.headers, self.ids = db, headers, ids
        self.client = TestClient(app)

    # ---- HTTP helpers
    def tool(self, tool, who=SENIOR, env="production", svc=SVC, extra=None, rid=None, client=None):
        rid = rid or ("QA-AF-" + uuid.uuid4().hex)[:32]
        args = {"service_name": svc, "environment": env, **(extra or {})}
        body = {"request_id": rid, "user_id": who, "agent_id": "AG001", "tool": tool, "arguments": args}
        return rid, (client or self.client).post(TOOL_PATH, json=body, headers=self.headers(who))

    def deploy(self, **kw):
        kw.setdefault("extra", {"target_version": 4})
        return self.tool("deploy_service", **kw)

    def listing(self, who=ADMIN, status=None):
        params = {"status": status} if status else None
        return self.client.get("/api/approvals", params=params, headers=self.headers(who))

    def approve(self, approval_id, who=ADMIN, reason="looks fine"):
        return self.client.post(f"/api/approvals/{approval_id}/approve", json={"reason": reason},
                                headers=self.headers(who))

    def reject(self, approval_id, who=ADMIN, reason="too risky"):
        return self.client.post(f"/api/approvals/{approval_id}/reject", json={"reason": reason},
                                headers=self.headers(who))

    # ---- DB helpers (always re-read)
    def approval(self, rid):
        self.db.rollback()
        return self.db.query(ApprovalRequest).filter_by(request_id=rid).one()

    def approvals(self, rid):
        self.db.rollback()
        return self.db.query(ApprovalRequest).filter_by(request_id=rid).all()

    def sec(self, rid):
        self.db.rollback()
        return self.db.get(SecurityRequest, rid)

    def risk(self, rid):
        self.db.rollback()
        return self.db.query(RiskAssessment).filter_by(request_id=rid).one()

    def events(self, rid):
        self.db.rollback()
        return self.db.query(BehaviorEvent).filter_by(request_id=rid).all()

    def service(self, key):
        self.db.rollback()
        return self.db.get(Service, self.ids[key])

    def history(self, key, change_type=None):
        self.db.rollback()
        q = self.db.query(ServiceStateHistory).filter_by(service_id=self.ids[key])
        if change_type is not None:
            q = q.filter_by(change_type=change_type)
        return q.order_by(ServiceStateHistory.id).all()

    def bump(self, key, **fields):
        """Change service state from a SEPARATE connection (a concurrent action)."""
        other = SessionLocal()
        try:
            row = other.get(Service, self.ids[key])
            for name, value in fields.items():
                setattr(row, name, value)
            other.commit()
        finally:
            other.close()
        self.db.expire_all()


@pytest.fixture
def af(db, make_user, ag001_agent, auth_headers):
    senior = make_user(SENIOR, Role.SENIOR_DEVELOPER)
    admin = make_user(ADMIN, Role.ADMIN)
    make_user(ADMIN2, Role.ADMIN)
    make_user(JUNIOR, Role.JUNIOR_DEVELOPER)
    made = {
        "stg": Service(service_name=SVC, environment=STAGING, current_version=3, known_good_version=2,
                       owner_id=senior.id, status="healthy"),
        "prod": Service(service_name=SVC, environment=PRODUCTION, current_version=3,
                        known_good_version=2, owner_id=senior.id, status="healthy"),
        "aprod": Service(service_name=ADMIN_SVC, environment=PRODUCTION, current_version=3,
                         known_good_version=2, owner_id=admin.id, status="healthy"),
    }
    db.add_all(made.values())
    db.commit()
    ids = {k: v.id for k, v in made.items()}
    yield AF(db, auth_headers, ids)
    db.rollback()
    delete_requests(db, SecurityRequest.request_id.like("QA-AF-%"))
    sids = list(ids.values())
    db.query(ServiceStateHistory).filter(ServiceStateHistory.service_id.in_(sids)).delete(
        synchronize_session=False)
    db.query(Service).filter(Service.id.in_(sids)).delete(synchronize_session=False)
    db.commit()


# ------------------------------------------------------------------ Demo 4, end to end
def test_demo4_production_deploy_request_then_approve_then_execute(af):
    rid, resp = af.deploy()
    # --- request time: nothing ran
    assert resp.status_code == 200
    assert resp.json() == {"request_id": rid, "decision": "APPROVAL_REQUIRED", "reason": APPROVAL_REASON}
    assert af.service("prod").current_version == 3 and af.history("prod") == []
    sec = af.sec(rid)
    assert sec.decision is Decision.APPROVAL_REQUIRED and sec.execution_status is ExecutionStatus.NOT_EXECUTED
    approval = af.approval(rid)
    assert approval.status is ApprovalStatus.PENDING
    assert approval.state_snapshot == {"current_version": 3, "known_good_version": 2}
    (pending,) = af.events(rid)
    assert pending.outcome is EventOutcome.PENDING

    # --- the admin sees it, with risk (#79, #83)
    listing = af.listing().json()
    (item,) = [i for i in listing if i["request_id"] == rid]
    assert set(item) == LIST_KEYS
    assert item["requester"] == SENIOR and item["agent"] == "AG001" and item["tool"] == "deploy_service"
    assert item["service_name"] == SVC and item["environment"] == "production"
    assert item["arguments"]["target_version"] == 4
    assert item["risk"]["final_risk_level"] == "HIGH" and COND_REQUIRES_APPROVAL in item["risk"]["reasons"]

    # --- approve: revalidate (flag still set: no loop), MCP runs, state changes
    done = af.approve(approval.id)
    assert done.status_code == 200
    body = done.json()
    assert (body["approval_status"], body["outcome"]) == ("approved", "executed")
    assert body["request_id"] == rid and body["result"]["result"]["version_after"] == 4
    service = af.service("prod")
    assert (service.current_version, service.known_good_version) == (4, 3)  # #9
    (hist,) = af.history("prod", ChangeType.DEPLOY)
    assert (hist.version_before, hist.version_after) == (3, 4)

    # --- evidence
    approval = af.approval(rid)
    assert approval.status is ApprovalStatus.APPROVED and approval.revalidation == "passed"
    assert approval.reviewer_id is not None and approval.decided_at is not None
    assert approval.reason == "looks fine"
    assert len(af.approvals(rid)) == 1  # no approval loop
    sec = af.sec(rid)
    assert sec.execution_status is ExecutionStatus.EXECUTED
    assert sec.decision is Decision.APPROVAL_REQUIRED  # never rewritten (#80)
    (event,) = af.events(rid)  # ONE row, resolved in place (#85)
    assert (event.outcome, event.version_before, event.version_after) == (EventOutcome.ALLOWED, 3, 4)


def test_production_restart_is_medium_approved_and_executed(af):
    rid, resp = af.tool("restart_service")
    assert resp.json()["decision"] == "APPROVAL_REQUIRED"
    assert af.risk(rid).reasons == ["production_targeting:medium", MARKER_ML_STUB]
    done = af.approve(af.approval(rid).id)
    assert done.status_code == 200 and done.json()["outcome"] == "executed"
    assert len(af.history("prod", ChangeType.RESTART)) == 1
    (event,) = af.events(rid)
    assert event.outcome is EventOutcome.ALLOWED and event.version_before is None


def test_mcp_is_not_called_until_approval_and_gets_the_stored_arguments(af):
    fake = Scripted()
    use_mcp(fake)
    rid, resp = af.deploy()
    assert resp.json()["decision"] == "APPROVAL_REQUIRED" and fake.calls == []
    assert af.approve(af.approval(rid).id).status_code == 200
    assert fake.calls == [(rid, "deploy_service",
                           {"service_name": SVC, "environment": "production", "target_version": 4})]


# ------------------------------------------------------------------ reject
def test_reject_runs_nothing_and_never_revalidates(af):
    fake = Scripted()
    use_mcp(fake)
    rid, _ = af.deploy()
    res = af.reject(af.approval(rid).id, reason="not this week")
    assert res.status_code == 200
    assert res.json()["approval_status"] == "rejected" and res.json()["outcome"] == "rejected"
    assert fake.calls == [] and af.history("prod") == []
    approval = af.approval(rid)
    assert approval.status is ApprovalStatus.REJECTED and approval.reason == "not this week"
    assert approval.revalidation is None  # revalidation never ran (#84)
    assert approval.decided_at is not None and approval.reviewer_id is not None
    assert af.sec(rid).execution_status is ExecutionStatus.NOT_EXECUTED
    (event,) = af.events(rid)
    assert event.outcome is EventOutcome.BLOCKED
    assert af.approve(approval.id).status_code == 409  # a rejected request cannot be approved


@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}, None])
def test_reject_without_a_reason_is_422_and_stays_pending(af, body):
    rid, _ = af.deploy()
    approval_id = af.approval(rid).id
    res = af.client.post(f"/api/approvals/{approval_id}/reject", json=body, headers=af.headers(ADMIN))
    assert res.status_code == 422
    assert af.approval(rid).status is ApprovalStatus.PENDING


# ------------------------------------------------------------------ TOCTOU (Demo 10)
def test_state_change_between_request_and_approval_is_re_blocked(af):
    fake = Scripted()
    use_mcp(fake)
    rid, _ = af.deploy()
    af.bump("prod", current_version=4)  # a concurrent action changes the target service
    res = af.approve(af.approval(rid).id)
    assert res.status_code == 200
    body = res.json()
    assert (body["approval_status"], body["outcome"]) == ("approved", "revalidation_failed")
    assert "current_version 3 -> 4" in body["reason"] and body["reason"].startswith("Revalidation stage:")
    assert fake.calls == [] and af.history("prod") == []  # MCP never ran
    approval = af.approval(rid)
    assert approval.status is ApprovalStatus.APPROVED and approval.revalidation == body["reason"]
    sec = af.sec(rid)
    assert sec.execution_status is ExecutionStatus.NOT_EXECUTED and sec.decision is Decision.APPROVAL_REQUIRED
    (event,) = af.events(rid)
    assert event.outcome is EventOutcome.BLOCKED
    assert af.approve(approval.id).status_code == 409  # not re-runnable


def test_ownership_change_between_request_and_approval_is_re_blocked(af):
    rid, _ = af.deploy()
    af.bump("prod", owner_id=af.service("aprod").owner_id)  # reassigned to the admin
    res = af.approve(af.approval(rid).id)
    assert res.json()["outcome"] == "revalidation_failed" and "Ownership stage" in res.json()["reason"]
    assert af.history("prod") == []


def test_policy_change_between_request_and_approval_is_re_blocked(af, db):
    rid, _ = af.deploy()
    senior = db.query(User).filter_by(username=SENIOR).one()  # the requester
    senior.role = Role.JUNIOR_DEVELOPER  # role is read from the DB each time (#44)
    db.commit()
    res = af.approve(af.approval(rid).id)
    assert res.json()["outcome"] == "revalidation_failed" and "Policy stage" in res.json()["reason"]
    assert af.history("prod") == []


# ------------------------------------------------------------------ auth and errors
def test_listing_requires_authentication_and_admin(af):
    assert af.client.get("/api/approvals").status_code == 401
    assert af.client.get("/api/approvals", headers={"Authorization": "Bearer not.a.jwt"}).status_code == 401
    for who in (SENIOR, JUNIOR):
        res = af.listing(who=who)
        assert res.status_code == 403 and res.json() == {"detail": "Forbidden."}


def test_non_admin_cannot_approve_or_reject(af):
    rid, _ = af.deploy()
    approval_id = af.approval(rid).id
    assert af.approve(approval_id, who=SENIOR).status_code == 403  # the requester themself
    assert af.reject(approval_id, who=JUNIOR).status_code == 403
    assert af.client.post(f"/api/approvals/{approval_id}/approve").status_code == 401
    assert af.approval(rid).status is ApprovalStatus.PENDING


def test_unknown_approval_id_is_404(af):
    assert af.approve(2_000_000_000).status_code == 404
    assert af.reject(2_000_000_000).status_code == 404


def test_invalid_status_filter_is_422(af):
    assert af.listing(status="everything").status_code == 422


def test_double_approve_is_409_and_mcp_runs_once(af):
    rid, _ = af.deploy()
    approval_id = af.approval(rid).id
    assert af.approve(approval_id).status_code == 200
    first = af.approval(rid)
    first_reviewer, first_reason, first_decided = first.reviewer_id, first.reason, first.decided_at
    again = af.approve(approval_id, who=ADMIN2, reason="second try")
    assert again.status_code == 409
    assert len(af.history("prod", ChangeType.DEPLOY)) == 1
    assert af.service("prod").current_version == 4
    second = af.approval(rid)  # the first decision is untouched
    assert (second.reviewer_id, second.reason, second.decided_at) == (first_reviewer, first_reason, first_decided)


# ------------------------------------------------------------------ self-approval (#82)
def test_admin_cannot_approve_own_request_but_can_reject_it_and_another_admin_can_approve(af):
    rid, resp = af.tool("restart_service", who=ADMIN, svc=ADMIN_SVC)
    assert resp.json()["decision"] == "APPROVAL_REQUIRED"
    approval_id = af.approval(rid).id
    own = af.approve(approval_id, who=ADMIN)
    assert own.status_code == 403
    assert af.approval(rid).status is ApprovalStatus.PENDING and af.history("aprod") == []
    assert af.approve(approval_id, who=ADMIN2).status_code == 200
    assert len(af.history("aprod", ChangeType.RESTART)) == 1

    rid2, _ = af.tool("restart_service", who=ADMIN, svc=ADMIN_SVC)
    cancelled = af.reject(af.approval(rid2).id, who=ADMIN, reason="cancel my own")
    assert cancelled.status_code == 200 and cancelled.json()["outcome"] == "rejected"


# ------------------------------------------------------------------ MCP failure after approval
@pytest.mark.parametrize("fake", [Scripted(status=500), Scripted(raises=True)], ids=["http500", "unavailable"])
def test_mcp_failure_after_approval_is_502_and_recorded_as_failed(af, fake):
    use_mcp(fake)
    rid, _ = af.deploy()
    res = af.approve(af.approval(rid).id)
    assert res.status_code == 502 and "MCP execution failed" in res.json()["detail"]
    approval = af.approval(rid)
    assert approval.status is ApprovalStatus.APPROVED and approval.revalidation == "passed"
    assert af.sec(rid).execution_status is ExecutionStatus.FAILED
    (event,) = af.events(rid)
    assert event.outcome is EventOutcome.FAILED and event.version_before is None
    assert af.approve(approval.id).status_code == 409  # a failed request is not retried by replay


# ------------------------------------------------------------------ one commit (#80)
def test_a_failed_approval_row_write_rolls_back_the_whole_request(af, monkeypatch):
    fake = Scripted()
    use_mcp(fake)

    def broken(*args, **kwargs):
        raise RuntimeError("approval write failed")

    monkeypatch.setattr(audit, "create_pending", broken)
    rid, resp = af.deploy(client=TestClient(app, raise_server_exceptions=False))
    assert resp.status_code == 500 and fake.calls == []
    af.db.rollback()
    assert af.sec(rid) is None  # no audit row,
    assert af.db.query(RiskAssessment).filter_by(request_id=rid).count() == 0  # no risk row,
    assert af.approvals(rid) == [] and af.events(rid) == []  # no approval, no event


def test_duplicate_request_id_creates_no_second_approval(af):
    rid, first = af.deploy()
    _, second = af.deploy(rid=rid)
    assert first.status_code == 200 and second.status_code == 409
    assert len(af.approvals(rid)) == 1


# ------------------------------------------------------------------ listing
def test_listing_filters_by_status_and_is_oldest_first(af):
    rid1, _ = af.deploy()
    rid2, _ = af.tool("restart_service")
    pending = [i["request_id"] for i in af.listing().json() if i["request_id"] in (rid1, rid2)]
    assert pending == [rid1, rid2]
    af.reject(af.approval(rid1).id)
    pending = [i["request_id"] for i in af.listing().json() if i["request_id"] in (rid1, rid2)]
    assert pending == [rid2]
    rejected = [i for i in af.listing(status="rejected").json() if i["request_id"] == rid1]
    assert len(rejected) == 1 and rejected[0]["reviewer"] == ADMIN and rejected[0]["reason"] == "too risky"
    assert [i for i in af.listing(status="approved").json() if i["request_id"] in (rid1, rid2)] == []


def test_new_approval_rows_never_carry_the_interim_marker(af):
    rid, _ = af.deploy()
    assert MARKER_INTERIM_NOT_ENFORCED not in af.risk(rid).reasons
    assert af.risk(rid).decision is Decision.APPROVAL_REQUIRED


# ------------------------------------------------------------------ #86 end to end
def test_an_approved_executed_deploy_counts_for_rule_s1(af):
    rid, _ = af.deploy()
    assert af.approve(af.approval(rid).id).status_code == 200
    rid2, resp = af.tool("rollback_deployment")  # same user, same service, within 10 minutes
    assert resp.json()["decision"] == "APPROVAL_REQUIRED"
    assert COND_S1 in af.risk(rid2).reasons  # visible only because executed no longer needs ALLOW (#86)


def test_each_event_row_is_written_once_per_request(af):
    rid, _ = af.deploy()
    assert len(af.events(rid)) == 1
    af.approve(af.approval(rid).id)
    assert len(af.events(rid)) == 1


# ------------------------------------------------------------------ the policy flag alone (#78)
def test_policy_flag_alone_forces_approval_even_for_a_low_risk_read(af, db):
    """Reads are LOW and exempt from every rule-risk row, so ONLY the policy flag can route
    this request. A stray approval-bound row for senior get_logs/staging does exactly that."""
    tool_id = db.query(Tool).filter_by(tool_name="get_logs").one().id
    stray = Policy(role=Role.SENIOR_DEVELOPER, tool_id=tool_id, environment=STAGING,
                   action="get_logs", allowed=True, requires_approval=True)
    db.add(stray)
    db.commit()
    stray_id = stray.id
    try:
        rid, resp = af.tool("get_logs", env="staging")
        assert resp.json()["decision"] == "APPROVAL_REQUIRED"
        assert resp.json()["reason"] == APPROVAL_REASON
        assert af.risk(rid).final_risk_level.value == "LOW"  # risk alone would have ALLOWed
        assert len(af.approvals(rid)) == 1
    finally:
        db.rollback()
        db.query(Policy).filter_by(id=stray_id).delete()
        db.commit()
