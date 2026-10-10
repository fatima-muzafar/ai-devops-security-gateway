"""
Phase 9 Stage 1: rule-based risk engine (decisions.md #53-#59, #62).

assess_risk() is pure and read-only; these tests never touch the pipeline except
test_denial_filter_matches_only_ownership_and_policy_blocks, which drives the REAL Gateway
to prove the structural #57 filter. History rows are inserted with explicit created_at
relative to a fixed NOW, so nothing depends on the wall clock. Request ids start with QA-R-.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, or_

from app.database.enums import Decision, Environment, ExecutionStatus, RiskLevel, Role, Sensitivity
from app.database.models import SecurityRequest, Service, ServiceStateHistory, Tool
from app.gateway import risk_constants as C
from app.gateway.risk import (
    COND_REPEATED_DENIALS,
    COND_REQUIRES_APPROVAL,
    COND_S1,
    COND_S2,
    COND_S3,
    MARKER_ML_STUB,
    assess_risk,
    qualifying_denial_clause,
)
from app.main import app

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
LOW, MEDIUM, HIGH = RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH
STAGING, PRODUCTION = Environment.STAGING, Environment.PRODUCTION
SENS = {  # decisions.md #1
    "get_logs": Sensitivity.LOW,
    "get_metrics": Sensitivity.LOW,
    "restart_service": Sensitivity.MEDIUM,
    "rollback_deployment": Sensitivity.HIGH,
    "deploy_service": Sensitivity.HIGH,
}
READS = ["get_logs", "get_metrics"]
STATE_CHANGING = ["restart_service", "rollback_deployment", "deploy_service"]
WINDOW = int(C.DENIAL_WINDOW.total_seconds())  # 600


class World:
    def __init__(self, db, user, other, svc_a, svc_b, svc_prod, tool_ids):
        self.db, self.user, self.other = db, user, other
        self.svc_a, self.svc_b, self.svc_prod = svc_a, svc_b, svc_prod
        self.tool_ids = tool_ids

    def add(
        self,
        tool="restart_service",
        *,
        user="me",
        svc="a",
        decision=Decision.ALLOW,
        status=ExecutionStatus.EXECUTED,
        age=60,
        tool_id=True,
        service_id=True,
        reason=None,
    ):
        who = {"me": self.user, "other": self.other, None: None}[user]
        service = {"a": self.svc_a, "b": self.svc_b, "prod": self.svc_prod}[svc]
        self.db.add(
            SecurityRequest(
                request_id=("QA-R-" + uuid.uuid4().hex)[:32],
                user_id=who.id if who else None,
                service_id=service.id if service_id else None,
                environment=service.environment,
                tool_id=self.tool_ids[tool] if tool_id else None,
                arguments={},
                raw_request={},
                decision=decision,
                reason=reason,
                execution_status=status,
                created_at=NOW - timedelta(seconds=age),
            )
        )
        self.db.commit()

    def denial(self, age, **kw):
        kw.setdefault("reason", "Ownership stage: user 'x' is not assigned.")
        self.add(
            "get_logs", decision=Decision.BLOCK, status=ExecutionStatus.NOT_EXECUTED, age=age, **kw
        )

    def executed_read(self, age=5):
        self.add("get_logs", age=age)  # an interleaved executed request breaks an S2 run

    def failed_allow(self, age):
        self.add("restart_service", status=ExecutionStatus.FAILED, age=age)

    def assess(self, tool="restart_service", env=STAGING, svc="a", user="me", **kw):
        service = {"a": self.svc_a, "b": self.svc_b, "prod": self.svc_prod}[svc]
        who = {"me": self.user, "other": self.other}[user]
        return assess_risk(
            self.db,
            user_id=who.id,
            tool_name=tool,
            sensitivity=SENS[tool],
            environment=env,
            service_id=service.id,
            now=NOW,
            **kw,
        )


@pytest.fixture
def w(db, make_user):
    me = make_user("qa_risk_user", Role.JUNIOR_DEVELOPER)
    other = make_user("qa_risk_other", Role.SENIOR_DEVELOPER)
    svcs = []
    for name, env, owner in [
        ("qa-risk-a", STAGING, me),
        ("qa-risk-b", STAGING, other),
        ("qa-risk-prod", PRODUCTION, me),
    ]:
        s = Service(
            service_name=name, environment=env, current_version=1, known_good_version=1,
            owner_id=owner.id, status="healthy",
        )
        db.add(s)
        svcs.append(s)
    db.commit()
    tool_ids = {t.tool_name: t.id for t in db.query(Tool).all()}
    yield World(db, me, other, *svcs, tool_ids)
    db.rollback()
    ids = [s.id for s in svcs]
    db.query(SecurityRequest).filter(SecurityRequest.service_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.query(ServiceStateHistory).filter(ServiceStateHistory.service_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.query(Service).filter(Service.id.in_(ids)).delete(synchronize_session=False)
    db.commit()


# --------------------------------------------------------------------------- #53 / #54 levels


def test_registry_sensitivities_match_assumed_table(db):
    """#1 guard: the sensitivities these tests assume are what the registry actually holds."""
    got = {t.tool_name: t.sensitivity for t in db.query(Tool).all()}
    for name, sens in SENS.items():
        assert got[name] == sens


@pytest.mark.parametrize("tool", READS)
@pytest.mark.parametrize("env,svc", [(STAGING, "a"), (PRODUCTION, "prod")])
def test_reads_are_low_everywhere(w, tool, env, svc):
    r = w.assess(tool, env, svc)
    assert (r.rule_risk_level, r.final_risk_level) == (LOW, LOW)
    assert r.is_production is (env is PRODUCTION)


@pytest.mark.parametrize("tool", READS)
def test_reads_exempt_from_every_condition(w, tool):
    for age in (10, 20, 30):
        w.denial(age)
    r = w.assess(tool, requires_approval=True)
    assert r.final_risk_level is LOW
    assert r.reasons == [MARKER_ML_STUB]


@pytest.mark.parametrize("tool", STATE_CHANGING)
def test_owned_staging_state_change_is_low(w, tool):
    r = w.assess(tool, STAGING, "a")
    assert (r.rule_risk_level, r.final_risk_level) == (LOW, LOW)
    assert r.is_production is False


def test_staging_stays_low_even_for_high_sensitivity_tools(w):
    """#54: sensitivity alone never raises a staging action."""
    assert SENS["deploy_service"] is Sensitivity.HIGH
    assert w.assess("deploy_service", STAGING, "a").final_risk_level is LOW


@pytest.mark.parametrize(
    "tool,expected", [("restart_service", MEDIUM), ("rollback_deployment", HIGH), ("deploy_service", HIGH)]
)
def test_production_state_change_level_follows_sensitivity(w, tool, expected):
    r = w.assess(tool, PRODUCTION, "prod")
    assert r.rule_risk_level is expected
    assert r.is_production is True


def test_production_floor_is_medium_even_for_a_low_sensitivity_state_change(w):
    r = assess_risk(
        w.db, user_id=w.user.id, tool_name="restart_service", sensitivity=Sensitivity.LOW,
        environment=PRODUCTION, service_id=w.svc_prod.id, now=NOW,
    )
    assert r.rule_risk_level is MEDIUM


def test_requires_approval_flag_is_high(w):
    r = w.assess("deploy_service", STAGING, "a", requires_approval=True)
    assert r.final_risk_level is HIGH
    assert COND_REQUIRES_APPROVAL in r.reasons


def test_highest_simultaneous_condition_wins(w):
    w.add("restart_service", age=30)
    w.add("restart_service", age=60)  # S3 = MEDIUM, production restart = MEDIUM
    assert w.assess("restart_service", PRODUCTION, "a").final_risk_level is MEDIUM
    for age in (3, 4, 5):  # strictly more recent than the S3 priors: no timestamp tie
        w.denial(age)  # S2 = HIGH on top
    assert w.assess("restart_service", PRODUCTION, "a").final_risk_level is HIGH


# --------------------------------------------------------------------------- #59 ML stub


def test_ml_is_a_low_stub_with_marker_and_final_equals_rule(w):
    for tool, env, svc in [("get_logs", STAGING, "a"), ("deploy_service", PRODUCTION, "prod")]:
        r = w.assess(tool, env, svc)
        assert r.ml_risk_level is LOW
        assert MARKER_ML_STUB in r.reasons
        assert r.final_risk_level is r.rule_risk_level


# --------------------------------------------------------------------------- #57 repeated denials


def test_two_denials_do_not_trigger(w):
    w.executed_read()
    w.denial(100)
    w.denial(200)
    assert COND_REPEATED_DENIALS not in w.assess().reasons


def test_three_denials_trigger_medium_when_not_consecutive(w):
    w.executed_read()  # breaks S2 so only the #57 count is under test
    for age in (100, 200, 300):
        w.denial(age)
    r = w.assess()
    assert COND_REPEATED_DENIALS in r.reasons and COND_S2 not in r.reasons
    assert r.final_risk_level is MEDIUM


def test_denial_window_boundary_is_inclusive(w):
    w.executed_read()
    w.denial(WINDOW)  # exactly at the boundary: counts
    w.denial(300)
    w.denial(400)
    assert COND_REPEATED_DENIALS in w.assess().reasons


def test_denial_just_outside_window_does_not_count(w):
    w.executed_read()
    w.denial(WINDOW + 1)
    w.denial(300)
    w.denial(400)
    assert COND_REPEATED_DENIALS not in w.assess().reasons


@pytest.mark.parametrize(
    "kw",
    [
        {"user": "other"},  # someone else's denials
        {"user": None},  # authentication-stage rows (user_id NULL)
        {"service_id": False},  # Arguments/Service/mismatched-claim rows
        {"tool_id": False},  # Tool-stage rows
    ],
    ids=["other_user", "null_user", "null_service", "null_tool"],
)
def test_non_qualifying_rows_are_not_denials(w, kw):
    w.executed_read()
    for age in (100, 200, 300):
        w.denial(age, **kw)
    assert COND_REPEATED_DENIALS not in w.assess().reasons


def test_failed_allows_are_not_denials(w):
    w.executed_read()
    for age in (100, 200, 300):
        w.failed_allow(age)
    assert COND_REPEATED_DENIALS not in w.assess().reasons


def test_denial_trigger_applies_to_state_changing_requests_only(w):
    w.executed_read()
    for age in (100, 200, 300):
        w.denial(age)
    assert w.assess("get_logs").final_risk_level is LOW


def test_denials_count_across_services_and_tools(w):
    w.executed_read()
    w.denial(100, svc="a")
    w.denial(200, svc="b")
    w.denial(300, svc="prod")
    assert COND_REPEATED_DENIALS in w.assess().reasons


# --------------------------------------------------------------------------- #56 / #62 S2


def test_s2_three_consecutive_denials_is_high_and_includes_the_57_trigger(w):
    for age in (10, 20, 30):
        w.denial(age)
    r = w.assess()
    assert r.final_risk_level is HIGH
    assert COND_S2 in r.reasons and COND_REPEATED_DENIALS in r.reasons


def test_s2_failed_allow_branch_fires_without_the_denial_trigger(w):
    w.failed_allow(10)
    w.denial(20)
    w.failed_allow(30)
    r = w.assess()
    assert COND_S2 in r.reasons and COND_REPEATED_DENIALS not in r.reasons
    assert r.final_risk_level is HIGH


def test_s2_needs_three(w):
    w.denial(10)
    w.denial(20)
    assert COND_S2 not in w.assess().reasons


def test_s2_executed_request_inside_the_run_breaks_it(w):
    w.denial(10)
    w.executed_read(20)
    w.denial(30)
    w.denial(40)
    assert COND_S2 not in w.assess().reasons


def test_s2_noise_row_breaks_the_run(w):
    """#62: a Tool-stage BLOCK (tool_id NULL) is not skipped; it resets the run."""
    w.add("get_logs", decision=Decision.BLOCK, status=ExecutionStatus.NOT_EXECUTED, age=10,
          tool_id=False, reason="Tool registry stage: x")
    for age in (20, 30, 40):
        w.denial(age)
    assert COND_S2 not in w.assess().reasons


def test_s2_window_boundary(w):
    w.denial(10)
    w.denial(20)
    w.denial(WINDOW)
    assert COND_S2 in w.assess().reasons


def test_s2_one_row_outside_window_does_not_fire(w):
    w.denial(10)
    w.denial(20)
    w.denial(WINDOW + 1)
    assert COND_S2 not in w.assess().reasons


def test_s2_spans_services_and_tools_per_user(w):
    w.denial(10, svc="a")
    w.denial(20, svc="b")
    w.failed_allow(30)
    assert COND_S2 in w.assess().reasons


def test_s2_ignores_other_users_rows(w):
    for age in (10, 20, 30):
        w.denial(age, user="other")
    assert COND_S2 not in w.assess().reasons


def test_s2_is_exempt_for_reads(w):
    for age in (10, 20, 30):
        w.denial(age)
    assert w.assess("get_logs").final_risk_level is LOW


# --------------------------------------------------------------------------- #56 S1


def test_s1_rollback_after_executed_deploy_is_medium(w):
    w.add("deploy_service", age=60)
    r = w.assess("rollback_deployment")
    assert COND_S1 in r.reasons and r.final_risk_level is MEDIUM


def test_s1_boundary_is_inclusive(w):
    w.add("deploy_service", age=int(C.S1_WINDOW.total_seconds()))
    assert COND_S1 in w.assess("rollback_deployment").reasons


@pytest.mark.parametrize(
    "row,incoming",
    [
        ({"age": 601}, "rollback_deployment"),  # outside the window
        ({"svc": "b"}, "rollback_deployment"),  # different service row
        ({"user": "other"}, "rollback_deployment"),  # different user
        ({"decision": Decision.BLOCK, "status": ExecutionStatus.NOT_EXECUTED}, "rollback_deployment"),
        ({"status": ExecutionStatus.FAILED}, "rollback_deployment"),  # never recorded as executed
        ({}, "restart_service"),  # S1 is rollback-only
        ({}, "deploy_service"),
    ],
    ids=["old", "other_service", "other_user", "blocked", "failed", "incoming_restart", "incoming_deploy"],
)
def test_s1_does_not_fire(w, row, incoming):
    w.add("deploy_service", **{"age": 60, **row})
    assert COND_S1 not in w.assess(incoming).reasons


def test_s1_needs_a_deploy_not_another_tool(w):
    w.add("restart_service", age=60)
    assert COND_S1 not in w.assess("rollback_deployment").reasons


# --------------------------------------------------------------------------- #56 S3


@pytest.mark.parametrize("tool", STATE_CHANGING)
def test_s3_third_identical_action_is_medium(w, tool):
    w.add(tool, age=30)
    w.add(tool, age=60)
    r = w.assess(tool)
    assert COND_S3 in r.reasons and r.final_risk_level is MEDIUM


def test_a_request_never_counts_itself(w):
    """One prior executed: if the incoming request counted itself this would reach 2."""
    w.add("restart_service", age=30)
    assert COND_S3 not in w.assess("restart_service").reasons
    w.executed_read()
    w.denial(100)
    w.denial(200)  # two priors, would be three if counted
    assert COND_REPEATED_DENIALS not in w.assess().reasons


def test_s3_window_boundary(w):
    secs = int(C.S3_WINDOW.total_seconds())
    w.add("restart_service", age=secs)
    w.add("restart_service", age=60)
    assert COND_S3 in w.assess().reasons


@pytest.mark.parametrize(
    "row",
    [
        {"age": 301},
        {"svc": "b"},
        {"user": "other"},
        {"tool": "deploy_service"},
        {"status": ExecutionStatus.FAILED},
        {"decision": Decision.BLOCK, "status": ExecutionStatus.NOT_EXECUTED},
    ],
    ids=["old", "other_service", "other_user", "other_tool", "failed", "blocked"],
)
def test_s3_does_not_count(w, row):
    w.add("restart_service", age=30)  # one valid prior
    w.add(**{"tool": "restart_service", "age": 60, **row})  # second one must not count
    assert COND_S3 not in w.assess("restart_service").reasons


# --------------------------------------------------------------------------- read-only + cost


def test_assess_risk_writes_nothing(w, db):
    before = db.query(SecurityRequest).count()
    for age in (10, 20, 30):
        w.denial(age)
    w.assess()
    assert db.query(SecurityRequest).count() == before + 3


def _count_selects(db, fn):
    statements = []

    def spy(conn, cursor, statement, *a):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", spy)
    try:
        fn()
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", spy)
    return len(statements)


def test_history_query_cost_per_request_for_e3(w, db):
    """Documents the per-request DB cost E3 must account for (STATUS.md close-out note)."""
    _ = (w.user.id, w.svc_a.id, w.svc_b.id, w.svc_prod.id)  # load ids: a refresh is not engine cost
    assert _count_selects(db, lambda: w.assess("get_logs")) == 0
    assert _count_selects(db, lambda: w.assess("restart_service")) == 3
    assert _count_selects(db, lambda: w.assess("deploy_service")) == 3
    assert _count_selects(db, lambda: w.assess("rollback_deployment")) == 4


# ------------------------------------------------------------ #57 filter vs the REAL pipeline

client = TestClient(app)
PATH = "/api/gateway/tool-request"


def test_denial_filter_matches_only_ownership_and_policy_blocks(w, db, auth_headers, ag001_agent):
    """#57 gate: the structural filter selects exactly the Ownership/Policy BLOCKs the real
    pipeline produces, and every matched row carries one of those reason prefixes."""
    me, other = w.user.username, w.other.username
    hdr = auth_headers(me)

    def post(tag, tool, args, headers=hdr, user_id=me):
        rid = ("QA-R-" + tag + uuid.uuid4().hex)[:32]
        body = {"request_id": rid, "user_id": user_id, "agent_id": "AG001", "tool": tool,
                "arguments": args}
        resp = client.post(PATH, json=body, headers=headers)
        assert resp.status_code == 200, resp.text
        return rid, resp.json()

    a = {"service_name": "qa-risk-a", "environment": "staging"}
    b = {"service_name": "qa-risk-b", "environment": "staging"}
    sent = {
        "ownership": post("own", "get_logs", b),  # me does not own b
        "policy": post("pol", "deploy_service", {**a, "target_version": 2}),  # junior owns a but may not deploy
        "tool": post("tool", "no_such_tool", a),
        "args": post("arg", "get_logs", {}),
        "service": post("svc", "get_logs", {"service_name": "qa-risk-missing", "environment": "staging"}),
        "auth": post("auth", "get_logs", a, headers={}),
        "mismatch": post("mis", "get_logs", a, user_id=other),
        "allow": post("ok", "get_logs", a),
    }
    reasons = {k: v[1].get("reason") for k, v in sent.items()}
    assert reasons["ownership"].startswith("Ownership stage:")
    assert reasons["policy"].startswith("Policy stage:")
    assert sent["allow"][1]["decision"] == "ALLOW"

    ids = [v[0] for v in sent.values()]
    rows = (
        db.query(SecurityRequest)
        .filter(SecurityRequest.request_id.in_(ids))
        .filter(qualifying_denial_clause(w.user.id))
        .all()
    )
    matched = {r.request_id for r in rows}
    assert matched == {sent["ownership"][0], sent["policy"][0]}
    for r in rows:
        assert r.reason.startswith(("Ownership stage:", "Policy stage:"))
    # the mismatched-claim row records the authenticated user but must NOT match (service_id NULL)
    mismatch_row = db.get(SecurityRequest, sent["mismatch"][0])
    assert mismatch_row.user_id == w.user.id and mismatch_row.service_id is None
    # cleanup of these audit rows is handled by the `w` and `make_user` fixtures