"""
Phase 11 Stage 1 (decisions.md #78-#86): pure/DB logic only, no HTTP and no MCP.
decide_from_risk, evaluate_policy, revalidation, the approvals service, the pending-event
update and the #86 history fix. Request ids start with QA-APR-. Fixtures depend on make_user,
so they tear down (approvals, events, requests, services) BEFORE the users are deleted.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect

from app.approvals import service as approvals
from app.approvals.service import (
    AlreadyDecidedError, ApprovalNotFoundError, NotAdminError, ReasonRequiredError,
    SelfApprovalError,
)
from app.database.base import SessionLocal
from app.database.enums import (
    ApprovalStatus, Decision, Environment, EventOutcome, EventSource, ExecutionStatus, Role,
    RiskLevel,
)
from app.database.models import (
    Agent, ApprovalRequest, BehaviorEvent, SecurityRequest, Service, ServiceStateHistory, Tool,
    User,
)
from app.gateway.behavior_log import record_behavior_event, resolve_pending_event
from app.gateway.decision import decide_from_risk
from app.gateway.policy import evaluate_policy
from app.gateway.revalidation import RevalidationResult, revalidate_approval, take_snapshot
from app.gateway.risk import COND_S1, COND_S3, assess_risk
from qa_cleanup import delete_requests

STAGING, PRODUCTION = Environment.STAGING, Environment.PRODUCTION
HOOK_LOGGER = "app.gateway.behavior_log"


# ---------------------------------------------------------------- world
class World:
    def __init__(self, db, agent_id, senior, admin, admin2, junior, stg, prod):
        self.db, self.agent_id = db, agent_id
        self.senior, self.admin, self.admin2, self.junior = senior, admin, admin2, junior
        self.stg, self.prod = stg, prod

    def tool(self, name):
        return self.db.query(Tool).filter_by(tool_name=name).one()

    def request(self, tool_name="deploy_service", service=None, arguments=None, user=None,
                agent_id=None, execution=ExecutionStatus.NOT_EXECUTED, decision=Decision.APPROVAL_REQUIRED,
                created_at=None):
        service = service or self.prod
        user = user or self.senior
        args = arguments
        if args is None:
            args = {"service_name": service.service_name, "environment": service.environment.value}
            if tool_name == "deploy_service":
                args["target_version"] = service.current_version + 1
        row = SecurityRequest(
            request_id="QA-APR-" + uuid.uuid4().hex[:20],
            user_id=user.id, agent_id=agent_id or self.agent_id, service_id=service.id,
            tool_id=self.tool(tool_name).id, environment=service.environment,
            arguments=args, raw_request={}, decision=decision, reason="pending",
            execution_status=execution,
        )
        if created_at is not None:
            row.created_at = created_at
        self.db.add(row)
        self.db.commit()
        return row

    def pending(self, **kw):
        """A request plus its pending approval row, snapshot taken from the CURRENT service."""
        row = self.request(**kw)
        service = self.db.get(Service, row.service_id)
        approval = approvals.create_pending(self.db, row.request_id, take_snapshot(service))
        self.db.commit()
        return approval

    def approved(self, **kw):
        approval = self.pending(**kw)
        approvals.decide(self.db, approval.id, self.admin, approve=True, reason="ok")
        return approval


@pytest.fixture
def aw(db, make_user, ag001_agent):
    senior = make_user("qa_apr_senior", Role.SENIOR_DEVELOPER)
    admin = make_user("qa_apr_admin", Role.ADMIN)
    admin2 = make_user("qa_apr_admin2", Role.ADMIN)
    junior = make_user("qa_apr_junior", Role.JUNIOR_DEVELOPER)
    stg = Service(service_name="qa-apr-svc", environment=STAGING, current_version=3,
                  known_good_version=2, owner_id=senior.id, status="healthy")
    prod = Service(service_name="qa-apr-svc", environment=PRODUCTION, current_version=3,
                   known_good_version=2, owner_id=senior.id, status="healthy")
    db.add_all([stg, prod])
    db.commit()
    ids = [stg.id, prod.id]
    yield World(db, ag001_agent.id, senior, admin, admin2, junior, stg, prod)
    db.rollback()
    delete_requests(db, SecurityRequest.service_id.in_(ids))
    db.query(BehaviorEvent).filter(BehaviorEvent.service_id.in_(ids)).delete(synchronize_session=False)
    db.query(ServiceStateHistory).filter(ServiceStateHistory.service_id.in_(ids)).delete(synchronize_session=False)
    db.query(Service).filter(Service.id.in_(ids)).delete(synchronize_session=False)
    db.commit()


def bump(db, service_id, **fields):
    """Change service state from a SEPARATE connection, like a concurrent action."""
    other = SessionLocal()
    try:
        row = other.get(Service, service_id)
        for k, v in fields.items():
            setattr(row, k, v)
        other.commit()
    finally:
        other.close()
    db.expire_all()


# ---------------------------------------------------------------- #78 decide_from_risk
@pytest.mark.parametrize("risk,flag,expected", [
    (RiskLevel.LOW, False, Decision.ALLOW),
    (RiskLevel.MEDIUM, False, Decision.APPROVAL_REQUIRED),
    (RiskLevel.HIGH, False, Decision.APPROVAL_REQUIRED),
    (RiskLevel.LOW, True, Decision.APPROVAL_REQUIRED),
    (RiskLevel.MEDIUM, True, Decision.APPROVAL_REQUIRED),
    (RiskLevel.HIGH, True, Decision.APPROVAL_REQUIRED),
])
def test_decide_from_risk_truth_table(risk, flag, expected):
    assert decide_from_risk(risk, flag) is expected


def test_decide_from_risk_never_returns_block():
    for risk in RiskLevel:
        for flag in (True, False):
            assert decide_from_risk(risk, flag) is not Decision.BLOCK  # no BLOCK-class yet (#54)


# ---------------------------------------------------------------- #78 evaluate_policy
def test_policy_senior_production_deploy_is_permitted_but_approval_bound(db):
    result = evaluate_policy(db, Role.SENIOR_DEVELOPER, "deploy_service", PRODUCTION)
    assert result.block_reason is None and result.requires_approval is True


def test_policy_senior_production_restart_is_permitted_without_flag(db):
    result = evaluate_policy(db, Role.SENIOR_DEVELOPER, "restart_service", PRODUCTION)
    assert result.block_reason is None and result.requires_approval is False


def test_policy_denied_pair_has_a_reason_and_no_flag(db):
    result = evaluate_policy(db, Role.JUNIOR_DEVELOPER, "deploy_service", STAGING)
    assert "Policy stage" in result.block_reason and result.requires_approval is False


# ---------------------------------------------------------------- #84 revalidation
def test_revalidation_passes_when_nothing_changed_and_flag_is_still_set(aw, db):
    # The policy row for senior production deploy STILL carries requires_approval=True.
    assert evaluate_policy(db, Role.SENIOR_DEVELOPER, "deploy_service", PRODUCTION).requires_approval
    approval = aw.approved()
    result = revalidate_approval(db, approval)
    assert result.ok is True and result.reason is None and result.stored_text == "passed"


@pytest.mark.parametrize("tool", ["restart_service", "rollback_deployment", "deploy_service"])
@pytest.mark.parametrize("field,value", [("current_version", 4), ("known_good_version", 3)])
def test_revalidation_fails_when_a_snapshot_field_changed(aw, db, tool, field, value):
    approval = aw.approved(tool_name=tool)
    bump(db, aw.prod.id, **{field: value})
    result = revalidate_approval(db, approval)
    assert result.ok is False
    assert result.reason.startswith("Revalidation stage: service state changed")
    assert field in result.reason


def test_revalidation_fails_when_snapshot_is_missing_a_field(aw, db):
    approval = aw.approved()
    approval.state_snapshot = {"current_version": 3}
    db.commit()
    result = revalidate_approval(db, approval)
    assert not result.ok and "known_good_version" in result.reason


def test_revalidation_fails_when_ownership_changed(aw, db):
    approval = aw.approved()
    bump(db, aw.prod.id, owner_id=aw.admin.id)
    result = revalidate_approval(db, approval)
    assert not result.ok and "Ownership stage" in result.reason


def test_revalidation_fails_when_policy_no_longer_permits(aw, db):
    approval = aw.approved()
    aw.senior.role = Role.JUNIOR_DEVELOPER  # role is read from the DB each time (#44)
    db.commit()
    result = revalidate_approval(db, approval)
    assert not result.ok and "Policy stage" in result.reason


def test_revalidation_fails_when_tool_disabled(aw, db):
    approval = aw.approved()
    tool = aw.tool("deploy_service")
    tool.enabled = False
    db.commit()
    try:
        result = revalidate_approval(db, approval)
    finally:
        tool.enabled = True
        db.commit()
    assert not result.ok and "Tool registry stage" in result.reason


def test_revalidation_fails_when_agent_is_not_active(aw, db):
    agent = Agent(agent_name="QA-APR-AGENT", status="active")
    db.add(agent)
    db.commit()
    try:
        approval = aw.approved(agent_id=agent.id)
        agent.status = "inactive"
        db.commit()
        result = revalidate_approval(db, approval)
        assert not result.ok and "agent" in result.reason
    finally:
        db.rollback()
        delete_requests(db, SecurityRequest.agent_id == agent.id)
        db.query(Agent).filter_by(id=agent.id).delete()
        db.commit()


def test_revalidation_fails_for_invalid_stored_arguments(aw, db):
    approval = aw.approved(arguments={"environment": "production"})
    result = revalidate_approval(db, approval)
    assert not result.ok and "Arguments stage" in result.reason


def test_revalidation_fails_when_requester_is_gone(aw, db):
    approval = aw.approved()
    sec = db.get(SecurityRequest, approval.request_id)
    sec.user_id = None
    db.commit()
    result = revalidate_approval(db, approval)
    assert not result.ok and "user no longer exists" in result.reason


def test_revalidation_fails_when_target_service_row_differs(aw, db):
    approval = aw.approved()
    sec = db.get(SecurityRequest, approval.request_id)
    sec.service_id = aw.stg.id  # args still say production
    db.commit()
    result = revalidate_approval(db, approval)
    assert not result.ok and "no longer the one" in result.reason


@pytest.mark.parametrize("status", [ExecutionStatus.EXECUTED, ExecutionStatus.FAILED])
def test_revalidation_fails_when_request_already_ran(aw, db, status):
    approval = aw.approved()
    db.get(SecurityRequest, approval.request_id).execution_status = status
    db.commit()
    result = revalidate_approval(db, approval)
    assert not result.ok and "already" in result.reason


def test_revalidation_refuses_pending_and_rejected_approvals(aw, db):
    pending = aw.pending()
    assert "not 'approved'" in revalidate_approval(db, pending).reason
    rejected = aw.pending()
    approvals.decide(db, rejected.id, aw.admin, approve=False, reason="no")
    assert "not 'approved'" in revalidate_approval(db, rejected).reason


def test_revalidation_is_read_only(aw, db):
    approval = aw.approved()
    revalidate_approval(db, approval)
    assert not db.new and not db.dirty
    assert approval.revalidation is None


# ---------------------------------------------------------------- #81 schema
def test_approval_requests_schema_matches_decision_81(db):
    insp = inspect(db.get_bind())
    cols = {c["name"] for c in insp.get_columns("approval_requests")}
    assert {"decided_at", "state_snapshot", "revalidation"} <= cols and "approved_at" not in cols
    uniques = {tuple(u["column_names"]) for u in insp.get_unique_constraints("approval_requests")}
    assert ("request_id",) in uniques


# ---------------------------------------------------------------- #80/#81 create_pending
def test_create_pending_adds_a_pending_row_and_does_not_commit(aw, db):
    row = aw.request()
    approval = approvals.create_pending(db, row.request_id, {"current_version": 3, "known_good_version": 2})
    assert approval in db.new
    db.rollback()
    assert db.query(ApprovalRequest).filter_by(request_id=row.request_id).count() == 0


def test_create_pending_defaults_and_unique_request_id(aw, db):
    approval = aw.pending()
    assert approval.status == ApprovalStatus.PENDING
    assert approval.reviewer_id is None and approval.decided_at is None and approval.revalidation is None
    assert approval.state_snapshot == {"current_version": 3, "known_good_version": 2}
    approvals.create_pending(db, approval.request_id, {"current_version": 1, "known_good_version": 1})
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


# ---------------------------------------------------------------- #82/#83 decide
def test_non_admin_cannot_decide(aw, db):
    approval = aw.pending()
    for user in (aw.senior, aw.junior):
        with pytest.raises(NotAdminError):
            approvals.decide(db, approval.id, user, approve=True, reason="x")
    assert db.get(ApprovalRequest, approval.id).status == ApprovalStatus.PENDING


def test_unknown_approval_id_is_not_found(aw, db):
    with pytest.raises(ApprovalNotFoundError):
        approvals.decide(db, 2_000_000_000, aw.admin, approve=True, reason=None)


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_reject_requires_a_reason(aw, db, reason):
    approval = aw.pending()
    with pytest.raises(ReasonRequiredError):
        approvals.decide(db, approval.id, aw.admin, approve=False, reason=reason)
    assert db.get(ApprovalRequest, approval.id).status == ApprovalStatus.PENDING


def test_approve_does_not_require_a_reason(aw, db):
    approval = aw.pending()
    done = approvals.decide(db, approval.id, aw.admin, approve=True, reason=None)
    assert done.status == ApprovalStatus.APPROVED and done.reason is None


def test_requester_admin_cannot_approve_own_request_but_can_reject_it(aw, db):
    own = aw.pending(user=aw.admin, tool_name="restart_service")
    # admin is not the owner of the prod row, but self-approval is checked on the requester id
    with pytest.raises(SelfApprovalError):
        approvals.decide(db, own.id, aw.admin, approve=True, reason="me")
    assert db.get(ApprovalRequest, own.id).status == ApprovalStatus.PENDING
    done = approvals.decide(db, own.id, aw.admin, approve=False, reason="cancel")
    assert done.status == ApprovalStatus.REJECTED


def test_another_admin_can_approve_an_admins_request(aw, db):
    own = aw.pending(user=aw.admin, tool_name="restart_service")
    done = approvals.decide(db, own.id, aw.admin2, approve=True, reason="ok")
    assert done.status == ApprovalStatus.APPROVED


def test_decide_records_reviewer_reason_and_timestamp(aw, db):
    approval = aw.pending()
    stamp = datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc)
    done = approvals.decide(db, approval.id, aw.admin, approve=True, reason="looks fine", now=stamp)
    assert (done.reviewer_id, done.reason, done.decided_at) == (aw.admin.id, "looks fine", stamp)


def test_reject_records_reviewer_reason_and_timestamp(aw, db):
    approval = aw.pending()
    stamp = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
    done = approvals.decide(db, approval.id, aw.admin, approve=False, reason="too risky", now=stamp)
    assert (done.status, done.reviewer_id, done.decided_at) == (ApprovalStatus.REJECTED, aw.admin.id, stamp)


@pytest.mark.parametrize("first,second", [(True, True), (True, False), (False, True), (False, False)])
def test_second_decision_is_refused_and_changes_nothing(aw, db, first, second):
    approval = aw.pending()
    approvals.decide(db, approval.id, aw.admin, approve=first, reason="first")
    with pytest.raises(AlreadyDecidedError):
        approvals.decide(db, approval.id, aw.admin2, approve=second, reason="second")
    row = db.get(ApprovalRequest, approval.id)
    assert row.reviewer_id == aw.admin.id and row.reason == "first"


def test_decision_is_atomic_when_another_connection_decided_first(aw, db):
    approval = aw.pending()
    db.get(ApprovalRequest, approval.id)  # this session has seen status=pending
    other = SessionLocal()
    try:
        approvals.decide(other, approval.id, other.get(User, aw.admin2.id), approve=True, reason="winner")
    finally:
        other.close()
    with pytest.raises(AlreadyDecidedError):
        approvals.decide(db, approval.id, aw.admin, approve=False, reason="loser")
    db.expire_all()
    row = db.get(ApprovalRequest, approval.id)
    assert row.status == ApprovalStatus.APPROVED and row.reviewer_id == aw.admin2.id


# ---------------------------------------------------------------- #84 process_decision
class Spy:
    def __init__(self, ok=True):
        self.calls, self.ok = 0, ok

    def __call__(self, db, approval):
        self.calls += 1
        return RevalidationResult(True) if self.ok else RevalidationResult(False, "Revalidation stage: spy says no.")


def test_approve_runs_revalidation_once_and_stores_passed(aw, db):
    approval = aw.pending()
    spy = Spy()
    out = approvals.process_decision(db, approval.id, aw.admin, approve=True, reason=None, revalidate_fn=spy)
    assert spy.calls == 1 and out.revalidation.ok
    assert out.approval.status == ApprovalStatus.APPROVED and out.approval.revalidation == "passed"


def test_approve_with_failed_revalidation_stays_approved_and_stores_reason(aw, db):
    approval = aw.pending()
    out = approvals.process_decision(db, approval.id, aw.admin, approve=True, reason=None,
                                     revalidate_fn=Spy(ok=False))
    assert not out.revalidation.ok
    assert out.approval.status == ApprovalStatus.APPROVED
    assert out.approval.revalidation == "Revalidation stage: spy says no."


def test_reject_never_runs_revalidation(aw, db):
    approval = aw.pending()
    spy = Spy()
    out = approvals.process_decision(db, approval.id, aw.admin, approve=False, reason="no", revalidate_fn=spy)
    assert spy.calls == 0 and out.revalidation is None
    assert out.approval.status == ApprovalStatus.REJECTED and out.approval.revalidation is None


def test_refused_decisions_never_run_revalidation(aw, db):
    approval = aw.pending()
    spy = Spy()
    with pytest.raises(NotAdminError):
        approvals.process_decision(db, approval.id, aw.senior, approve=True, reason=None, revalidate_fn=spy)
    own = aw.pending(user=aw.admin, tool_name="restart_service")
    with pytest.raises(SelfApprovalError):
        approvals.process_decision(db, own.id, aw.admin, approve=True, reason=None, revalidate_fn=spy)
    approvals.process_decision(db, approval.id, aw.admin, approve=True, reason=None, revalidate_fn=spy)
    assert spy.calls == 1
    with pytest.raises(AlreadyDecidedError):
        approvals.process_decision(db, approval.id, aw.admin2, approve=True, reason=None, revalidate_fn=spy)
    assert spy.calls == 1  # the replayed approval did not revalidate again


def test_process_decision_with_the_real_revalidation(aw, db):
    ok = aw.pending()
    out = approvals.process_decision(db, ok.id, aw.admin, approve=True, reason=None)
    assert out.approval.revalidation == "passed"
    stale = aw.pending(tool_name="restart_service")
    bump(db, aw.prod.id, current_version=9)
    out = approvals.process_decision(db, stale.id, aw.admin, approve=True, reason=None)
    assert not out.revalidation.ok and "current_version 3 -> 9" in out.approval.revalidation


def test_real_revalidation_never_runs_for_a_rejected_request(aw, db, monkeypatch):
    calls = []
    monkeypatch.setattr(approvals, "revalidate_approval", lambda *a: calls.append(a))
    approval = aw.pending()
    out = approvals.process_decision(db, approval.id, aw.admin, approve=False, reason="no")
    assert calls == [] and out.approval.revalidation is None


# ---------------------------------------------------------------- #85 resolve_pending_event
def hook_records(caplog):
    return [r for r in caplog.records if r.name == HOOK_LOGGER]


def log_pending(aw, db, tool_name="deploy_service", service=None):
    service = service or aw.prod
    sec = aw.request(tool_name=tool_name, service=service)
    verdict = SimpleNamespace(user_id=aw.senior.id, agent_id=aw.agent_id, tool_id=aw.tool(tool_name).id,
                              service_id=service.id, environment=service.environment)
    stamp = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc)
    record_behavior_event(db, verdict, request_id=sec.request_id, timestamp=stamp,
                          outcome=EventOutcome.PENDING)
    return sec.request_id, stamp


def events(db, request_id):
    db.expire_all()
    return db.query(BehaviorEvent).filter_by(request_id=request_id).all()


def test_pending_event_is_written_by_the_existing_hook(aw, db):
    rid, stamp = log_pending(aw, db)
    (ev,) = events(db, rid)
    assert ev.outcome == EventOutcome.PENDING and ev.version_before is None and ev.timestamp == stamp


def test_resolve_allowed_deploy_copies_versions_and_keeps_timestamp(aw, db):
    rid, stamp = log_pending(aw, db)
    resolve_pending_event(db, rid, EventOutcome.ALLOWED,
                          result={"result": {"version_before": 3, "version_after": 4}})
    (ev,) = events(db, rid)  # still ONE row for the request
    assert (ev.outcome, ev.version_before, ev.version_after) == (EventOutcome.ALLOWED, 3, 4)
    assert ev.timestamp == stamp and ev.source == EventSource.LIVE


def test_resolve_allowed_restart_stores_null_versions(aw, db):
    rid, _ = log_pending(aw, db, tool_name="restart_service")
    resolve_pending_event(db, rid, EventOutcome.ALLOWED,
                          result={"result": {"version_before": 3, "version_after": 4}})
    (ev,) = events(db, rid)
    assert ev.outcome == EventOutcome.ALLOWED and ev.version_before is None and ev.version_after is None


@pytest.mark.parametrize("outcome", [EventOutcome.FAILED, EventOutcome.BLOCKED])
def test_resolve_failed_or_blocked_stores_null_versions(aw, db, outcome):
    rid, _ = log_pending(aw, db)
    resolve_pending_event(db, rid, outcome, result={"result": {"version_before": 3, "version_after": 4}})
    (ev,) = events(db, rid)
    assert ev.outcome == outcome and ev.version_before is None and ev.version_after is None


def test_resolve_allowed_without_integer_versions_stores_null_and_warns(aw, db, caplog):
    rid, _ = log_pending(aw, db)
    with caplog.at_level(logging.WARNING, logger=HOOK_LOGGER):
        resolve_pending_event(db, rid, EventOutcome.ALLOWED, result={"result": {}})
    (ev,) = events(db, rid)
    assert ev.outcome == EventOutcome.ALLOWED and ev.version_before is None
    assert hook_records(caplog)


def test_resolve_without_a_pending_row_only_warns(aw, db, caplog):
    with caplog.at_level(logging.WARNING, logger=HOOK_LOGGER):
        resolve_pending_event(db, "QA-APR-nothing", EventOutcome.ALLOWED, result=None)
    assert hook_records(caplog) and events(db, "QA-APR-nothing") == []


def test_a_resolved_row_is_not_resolved_twice(aw, db, caplog):
    rid, _ = log_pending(aw, db)
    resolve_pending_event(db, rid, EventOutcome.BLOCKED)
    with caplog.at_level(logging.WARNING, logger=HOOK_LOGGER):
        resolve_pending_event(db, rid, EventOutcome.ALLOWED, result={"result": {"version_before": 3, "version_after": 4}})
    (ev,) = events(db, rid)
    assert ev.outcome == EventOutcome.BLOCKED and hook_records(caplog)


@pytest.mark.parametrize("bad", [EventOutcome.PENDING])
def test_resolve_rejects_a_non_final_outcome(aw, db, bad):
    with pytest.raises(ValueError):
        resolve_pending_event(db, "QA-APR-x", bad)


def test_resolve_is_fail_open(caplog):
    class Boom:
        rolled_back = False

        def query(self, *a, **k):
            raise RuntimeError("db down")

        def rollback(self):
            Boom.rolled_back = True

    with caplog.at_level(logging.WARNING, logger=HOOK_LOGGER):
        resolve_pending_event(Boom(), "QA-APR-x", EventOutcome.ALLOWED)  # must not raise
    assert Boom.rolled_back and hook_records(caplog)


# ---------------------------------------------------------------- #86 executed history
def sensitivity(db, tool_name):
    return db.query(Tool).filter_by(tool_name=tool_name).one().sensitivity


def test_approved_executed_deploy_counts_for_s1(aw, db):
    now = datetime.now(timezone.utc)
    aw.request(tool_name="deploy_service", service=aw.stg, decision=Decision.APPROVAL_REQUIRED,
               execution=ExecutionStatus.EXECUTED, created_at=now - timedelta(minutes=2))
    risk = assess_risk(db, user_id=aw.senior.id, tool_name="rollback_deployment",
                       sensitivity=sensitivity(db, "rollback_deployment"),
                       environment=STAGING, service_id=aw.stg.id, now=now)
    assert COND_S1 in risk.reasons and risk.rule_risk_level == RiskLevel.MEDIUM


def test_a_pending_or_unexecuted_deploy_does_not_count_for_s1(aw, db):
    now = datetime.now(timezone.utc)
    aw.request(tool_name="deploy_service", service=aw.stg, decision=Decision.APPROVAL_REQUIRED,
               execution=ExecutionStatus.NOT_EXECUTED, created_at=now - timedelta(minutes=2))
    risk = assess_risk(db, user_id=aw.senior.id, tool_name="rollback_deployment",
                       sensitivity=sensitivity(db, "rollback_deployment"),
                       environment=STAGING, service_id=aw.stg.id, now=now)
    assert COND_S1 not in risk.reasons


def test_approved_executed_restarts_count_for_s3(aw, db):
    now = datetime.now(timezone.utc)
    for minutes in (3, 2):
        aw.request(tool_name="restart_service", service=aw.stg, decision=Decision.APPROVAL_REQUIRED,
                   execution=ExecutionStatus.EXECUTED, created_at=now - timedelta(minutes=minutes))
    risk = assess_risk(db, user_id=aw.senior.id, tool_name="restart_service",
                       sensitivity=sensitivity(db, "restart_service"),
                       environment=STAGING, service_id=aw.stg.id, now=now)
    assert COND_S3 in risk.reasons


def test_allow_executed_still_counts_for_s3(aw, db):
    now = datetime.now(timezone.utc)
    for minutes in (3, 2):
        aw.request(tool_name="restart_service", service=aw.stg, decision=Decision.ALLOW,
                   execution=ExecutionStatus.EXECUTED, created_at=now - timedelta(minutes=minutes))
    risk = assess_risk(db, user_id=aw.senior.id, tool_name="restart_service",
                       sensitivity=sensitivity(db, "restart_service"),
                       environment=STAGING, service_id=aw.stg.id, now=now)
    assert COND_S3 in risk.reasons
