"""
Phase 10 Stage 2: the live behavior-event hook (decisions.md #66, #69, #70, #75).

Drives the REAL Gateway. Versions are checked against the REAL MCP seam (the autouse one);
failures and ordering use a scripted fake. Request ids start with QA-LH-.
"""
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.database.base import SessionLocal
from app.database.behavior import is_off_hours
from app.database.enums import Environment, EventOutcome, EventSource, Role
from app.database.models import (
    Agent, BehaviorEvent, SecurityRequest, Service, ServiceStateHistory, Tool,
)
from app.gateway.mcp_client import McpResponse, McpUnavailableError, get_mcp_client
from app.main import app
from qa_cleanup import delete_requests

PATH = "/api/gateway/tool-request"
SENIOR, JUNIOR = "qa_lh_senior", "qa_lh_junior"
SVC, JSVC = "qa-lh-svc", "qa-lh-junior-svc"
STAGING, PRODUCTION = Environment.STAGING, Environment.PRODUCTION
HOOK_LOGGER = "app.gateway.behavior_log"


def hook_records(caplog):
    """Only the hook's own records: the pipeline legitimately logs MCP failures itself."""
    return [r for r in caplog.records if r.name == HOOK_LOGGER]


class Scripted:
    """Fake MCP. Records what a SEPARATE connection could see at the moment MCP is called."""

    def __init__(self, status=200, raises=False):
        self.status, self.raises, self.calls = status, raises, 0
        self.audit_at_call = self.events_at_call = None

    def execute(self, request_id, tool, arguments):
        self.calls += 1
        s = SessionLocal()
        try:
            self.audit_at_call = s.query(SecurityRequest).filter_by(request_id=request_id).count()
            self.events_at_call = s.query(BehaviorEvent).filter_by(request_id=request_id).count()
        finally:
            s.close()
        if self.raises:
            raise McpUnavailableError("down")
        if self.status == 200:
            return McpResponse(200, {"result": {"ok": True}})
        return McpResponse(self.status, {"detail": "boom"})


@contextmanager
def use_mcp(fake):
    previous = app.dependency_overrides.get(get_mcp_client)
    app.dependency_overrides[get_mcp_client] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides[get_mcp_client] = previous


class World:
    def __init__(self, db, headers, ids, users, agent_id):
        self.db, self._headers, self.ids, self.users, self.agent_id = db, headers, ids, users, agent_id
        self.client = TestClient(app)

    def post(self, tool, svc=SVC, env="staging", who=SENIOR, extra=None, rid=None,
             headers="auto", user_id=None, agent="AG001", arguments=None):
        rid = rid or ("QA-LH-" + uuid.uuid4().hex)[:32]
        args = arguments if arguments is not None else {
            "service_name": svc, "environment": env, **(extra or {})}
        body = {"request_id": rid, "user_id": user_id or who, "agent_id": agent,
                "tool": tool, "arguments": args}
        hdr = self._headers(who) if headers == "auto" else headers
        return rid, self.client.post(PATH, json=body, headers=hdr)

    def events(self, rid=None):
        self.db.rollback()
        q = self.db.query(BehaviorEvent)
        if rid is not None:
            q = q.filter_by(request_id=rid)
        else:
            q = q.filter(BehaviorEvent.identity_id.in_(self.users))
        return q.order_by(BehaviorEvent.timestamp, BehaviorEvent.id).all()

    def event(self, rid):
        rows = self.events(rid)
        assert len(rows) == 1, f"expected exactly one behavior event for {rid}, got {len(rows)}"
        return rows[0]

    def request_row(self, rid):
        self.db.rollback()
        return self.db.get(SecurityRequest, rid)

    def tool_name(self, ev):
        return self.db.get(Tool, ev.tool_id).tool_name


@pytest.fixture
def w(db, make_user, ag001_agent, auth_headers):
    senior = make_user(SENIOR, Role.SENIOR_DEVELOPER)
    junior = make_user(JUNIOR, Role.JUNIOR_DEVELOPER)
    made = [
        Service(service_name=SVC, environment=STAGING, current_version=1, known_good_version=1,
                owner_id=senior.id, status="healthy"),
        Service(service_name=SVC, environment=PRODUCTION, current_version=1, known_good_version=1,
                owner_id=senior.id, status="healthy"),
        Service(service_name=JSVC, environment=STAGING, current_version=1, known_good_version=1,
                owner_id=junior.id, status="healthy"),
    ]
    db.add_all(made)
    db.commit()
    ids = {"stg": made[0].id, "prod": made[1].id, "jstg": made[2].id}
    world = World(db, auth_headers, [senior.id, junior.id], {senior.id: SENIOR, junior.id: JUNIOR},
                  ag001_agent.id)
    world.ids, world.users = ids, [senior.id, junior.id]
    yield world
    db.rollback()
    delete_requests(db, SecurityRequest.request_id.like("QA-LH-%"))
    sids = list(ids.values())
    db.query(ServiceStateHistory).filter(ServiceStateHistory.service_id.in_(sids)).delete(
        synchronize_session=False)
    db.query(Service).filter(Service.id.in_(sids)).delete(synchronize_session=False)
    db.commit()


# ---- ALLOW: executed ---------------------------------------------------------------------
def test_allowed_read_is_logged_with_full_record(w, caplog):
    before = datetime.now(timezone.utc)
    with caplog.at_level(logging.WARNING, logger=HOOK_LOGGER):
        rid, resp = w.post("get_logs")
    after = datetime.now(timezone.utc)
    assert resp.status_code == 200 and resp.json()["decision"] == "ALLOW"
    ev = w.event(rid)
    assert ev.identity_id == w.users[0] and ev.agent_id == w.agent_id
    assert ev.service_id == w.ids["stg"] and ev.environment == STAGING
    assert w.tool_name(ev) == "get_logs" and ev.outcome == EventOutcome.ALLOWED
    assert (ev.version_before, ev.version_after) == (None, None)
    assert ev.source == EventSource.LIVE and ev.request_id == rid
    assert before <= ev.timestamp <= after  # captured at pipeline start, explicit, aware
    assert ev.off_hours_flag is is_off_hours(ev.timestamp)
    assert w.request_row(rid).execution_status.value == "executed"
    assert not hook_records(caplog)  # a normal path logs no warning


def test_restart_is_logged_with_null_versions(w, caplog):
    with caplog.at_level(logging.WARNING, logger=HOOK_LOGGER):
        rid, resp = w.post("restart_service")
    assert resp.json()["decision"] == "ALLOW"
    ev = w.event(rid)
    assert w.tool_name(ev) == "restart_service" and ev.outcome == EventOutcome.ALLOWED
    assert (ev.version_before, ev.version_after) == (None, None)
    assert not hook_records(caplog)


def test_deploy_and_rollback_copy_versions_from_the_real_mcp_result(w, caplog):
    with caplog.at_level(logging.WARNING, logger=HOOK_LOGGER):
        rid1, r1 = w.post("deploy_service", extra={"target_version": 2})
        rid2, r2 = w.post("rollback_deployment")
        rid3, r3 = w.post("deploy_service", extra={"target_version": 9})  # a large jump
    assert [r.json()["decision"] for r in (r1, r2, r3)] == ["ALLOW"] * 3
    e1, e2, e3 = w.event(rid1), w.event(rid2), w.event(rid3)
    assert (w.tool_name(e1), e1.version_before, e1.version_after) == ("deploy_service", 1, 2)
    assert (w.tool_name(e2), e2.version_before, e2.version_after) == ("rollback_deployment", 2, 1)
    assert (e3.version_before, e3.version_after) == (1, 9)
    assert all(e.outcome == EventOutcome.ALLOWED for e in (e1, e2, e3))
    # the stored versions agree with the mock environment's own transition log (#7: not derived
    # from it, only compared with it)
    hist = (w.db.query(ServiceStateHistory)
            .filter_by(service_id=w.ids["stg"]).order_by(ServiceStateHistory.id).all())
    assert [(h.version_before, h.version_after) for h in hist] == [(1, 2), (2, 1), (1, 9)]
    assert not hook_records(caplog)


def test_missing_versions_in_the_mcp_result_store_null_and_warn(w, caplog):
    with use_mcp(Scripted()), caplog.at_level(logging.WARNING, logger=HOOK_LOGGER):
        rid, resp = w.post("deploy_service", extra={"target_version": 2})
    assert resp.status_code == 200 and resp.json()["decision"] == "ALLOW"
    ev = w.event(rid)
    assert ev.outcome == EventOutcome.ALLOWED and (ev.version_before, ev.version_after) == (None, None)
    assert any("lacks integer version" in r.getMessage() for r in hook_records(caplog))


# ---- BLOCK: Ownership / Policy / interim approval-bound ----------------------------------
def test_ownership_block_is_logged_as_blocked(w):
    rid, resp = w.post("restart_service", svc=SVC, who=JUNIOR)  # SVC belongs to the senior
    assert resp.json()["decision"] == "BLOCK"
    assert w.request_row(rid).reason.startswith("Ownership stage:")
    ev = w.event(rid)
    assert ev.outcome == EventOutcome.BLOCKED and ev.identity_id == w.users[1]
    assert ev.service_id == w.ids["stg"] and (ev.version_before, ev.version_after) == (None, None)


def test_policy_block_is_logged_as_blocked(w):
    rid, resp = w.post("deploy_service", svc=JSVC, who=JUNIOR, extra={"target_version": 2})
    assert resp.json()["decision"] == "BLOCK"
    assert w.request_row(rid).reason.startswith("Policy stage:")
    ev = w.event(rid)
    assert ev.outcome == EventOutcome.BLOCKED and ev.service_id == w.ids["jstg"]


def test_interim_approval_bound_production_deploy_logs_blocked(w):
    rid, resp = w.post("deploy_service", env="production", extra={"target_version": 2})
    assert resp.json()["decision"] == "BLOCK"
    assert "requires human approval" in w.request_row(rid).reason
    ev = w.event(rid)
    assert ev.outcome == EventOutcome.BLOCKED and ev.environment == PRODUCTION


# ---- ALLOW + MCP failure -----------------------------------------------------------------
@pytest.mark.parametrize("fake", [Scripted(status=500), Scripted(raises=True)], ids=["http500", "unavailable"])
def test_mcp_failure_logs_failed_and_still_returns_502(w, caplog, fake):
    with use_mcp(fake), caplog.at_level(logging.WARNING, logger=HOOK_LOGGER):
        rid, resp = w.post("deploy_service", extra={"target_version": 2})
    assert resp.status_code == 502
    assert w.request_row(rid).execution_status.value == "failed"
    ev = w.event(rid)
    assert ev.outcome == EventOutcome.FAILED and (ev.version_before, ev.version_after) == (None, None)
    assert not hook_records(caplog)  # no spurious version warning on the failure path


# ---- NOT logged (#69) --------------------------------------------------------------------
NOT_LOGGED = {
    "no-token": dict(headers={}),
    "bad-token": dict(headers={"Authorization": "Bearer not.a.jwt"}),
    "mismatched-claim": dict(user_id="someone_else"),
    "unknown-tool": dict(tool="format_disk"),
    "missing-service-name": dict(arguments={"environment": "staging"}),
    "unknown-service": dict(svc="no-such-service"),
    "unknown-agent": dict(agent="NO-AGENT"),
}


@pytest.mark.parametrize("name", list(NOT_LOGGED))
def test_requests_without_a_resolved_identity_service_and_tool_are_not_logged(w, name, caplog):
    kw = dict(NOT_LOGGED[name])
    tool = kw.pop("tool", "restart_service")
    with caplog.at_level(logging.WARNING, logger=HOOK_LOGGER):
        rid, resp = w.post(tool, **kw)
    assert not hook_records(caplog)  # skipped by the filter, not by a swallowed error
    assert resp.status_code == 200 and resp.json()["decision"] == "BLOCK"
    assert w.request_row(rid) is not None  # audited ...
    assert w.events() == [] and w.events(rid) == []  # ... but not in behavior_events


def test_duplicate_request_id_and_unparseable_body_add_no_event(w):
    rid, first = w.post("get_logs")
    assert first.status_code == 200
    _, dup = w.post("get_logs", rid=rid)
    assert dup.status_code == 409
    bad = w.client.post(PATH, json={"request_id": "QA-LH-bad", "user_id": SENIOR},
                        headers=w._headers(SENIOR))
    assert bad.status_code == 422
    assert len(w.events()) == 1 and len(w.events(rid)) == 1


# ---- fail-open (#70) ---------------------------------------------------------------------
def test_writer_failure_never_changes_the_response_and_the_session_recovers(w, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("telemetry down")

    with monkeypatch.context() as m, caplog.at_level(logging.WARNING, logger=HOOK_LOGGER):
        m.setattr("app.gateway.behavior_log.add_behavior_event", boom)
        rid, allow = w.post("restart_service")
        brid, block = w.post("restart_service", who=JUNIOR)  # Ownership BLOCK path
    assert allow.status_code == 200 and allow.json()["decision"] == "ALLOW"
    assert set(allow.json()) == {"request_id", "decision", "result"}
    assert block.status_code == 200 and block.json()["decision"] == "BLOCK"
    assert set(block.json()) == {"request_id", "decision", "reason"}
    assert w.request_row(rid).execution_status.value == "executed"  # audit + MCP unaffected
    assert w.request_row(brid) is not None
    assert w.events() == []
    assert sum("behavior event write failed" in r.getMessage() for r in hook_records(caplog)) == 2
    rid2, ok = w.post("get_logs")  # the session is healthy afterwards
    assert ok.status_code == 200 and w.event(rid2).outcome == EventOutcome.ALLOWED


# ---- ordering and shape ------------------------------------------------------------------
def test_event_is_written_after_mcp_and_after_audit_commit(w):
    fake = Scripted()
    with use_mcp(fake):
        rid, resp = w.post("restart_service")
    assert resp.status_code == 200 and fake.calls == 1
    assert fake.audit_at_call == 1      # #35: audit committed before MCP
    assert fake.events_at_call == 0     # #70: outcome unknown pre-MCP, so no event yet
    assert w.event(rid).outcome == EventOutcome.ALLOWED


def test_one_event_per_request_and_one_window_per_identity_across_rows(w):
    for env in ("staging", "production", "staging", "production", "staging", "production"):
        _, resp = w.post("get_logs", env=env)
        assert resp.status_code == 200
    rows = w.events()
    assert len(rows) == 6 and len({r.request_id for r in rows}) == 6
    window = rows[-5:]  # #55: last 5 per identity, ordered by (timestamp, id), spans services
    assert {r.service_id for r in window} == {w.ids["stg"], w.ids["prod"]}
    assert all(r.identity_id == w.users[0] for r in rows)


def test_response_contract_is_unchanged(w):
    _, allow = w.post("get_logs")
    _, block = w.post("get_logs", who=JUNIOR)
    assert set(allow.json()) == {"request_id", "decision", "result"}
    assert set(block.json()) == {"request_id", "decision", "reason"}
