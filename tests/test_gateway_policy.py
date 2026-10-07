"""
Phase 8 Stage 3: Ownership and Policy stages (decisions.md #45-#48, #50, #52).

A module-scoped world creates 3 throwaway users (one per role) and 3 throwaway services
(one per role, each owning a staging AND a production row), so every role can reach the
Policy stage in both environments. MCP is stubbed: nothing here mutates mock state.
request_ids start with QA-P- (purged by prefix).
"""
from itertools import product

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import or_

from app.database.base import SessionLocal
from app.database.enums import Decision, Environment, ExecutionStatus, Role
from app.database.models import Policy, SecurityRequest, Service, ServiceStateHistory, Tool, User
from app.database.seed import SEED_POLICIES
from app.gateway.auth import issue_token
from app.gateway.mcp_client import McpResponse, get_mcp_client
from app.gateway.policy import check_policy
from app.main import app

client = TestClient(app)
PATH = "/api/gateway/tool-request"

JUNIOR_USER, SENIOR_USER, ADMIN_USER = "qa_pol_junior", "qa_pol_senior", "qa_pol_admin"
JUNIOR_SVC, SENIOR_SVC, ADMIN_SVC = "qa-pol-junior-svc", "qa-pol-senior-svc", "qa-pol-admin-svc"
USER_BY_ROLE = {
    Role.JUNIOR_DEVELOPER: JUNIOR_USER,
    Role.SENIOR_DEVELOPER: SENIOR_USER,
    Role.ADMIN: ADMIN_USER,
}
SERVICE_BY_ROLE = {
    Role.JUNIOR_DEVELOPER: JUNIOR_SVC,
    Role.SENIOR_DEVELOPER: SENIOR_SVC,
    Role.ADMIN: ADMIN_SVC,
}
TOOLS = ["get_logs", "get_metrics", "restart_service", "rollback_deployment", "deploy_service"]
ENVS = [Environment.STAGING, Environment.PRODUCTION]
USERNAMES = list(USER_BY_ROLE.values())
SERVICE_NAMES = list(SERVICE_BY_ROLE.values())


def _wipe(session):
    session.rollback()
    user_ids = [u.id for u in session.query(User).filter(User.username.in_(USERNAMES)).all()]
    service_ids = [
        s.id for s in session.query(Service).filter(Service.service_name.in_(SERVICE_NAMES)).all()
    ]
    conditions = []
    if user_ids:
        conditions.append(SecurityRequest.user_id.in_(user_ids))
    if service_ids:
        conditions.append(SecurityRequest.service_id.in_(service_ids))
    if conditions:
        session.query(SecurityRequest).filter(or_(*conditions)).delete(synchronize_session=False)
    if service_ids:
        session.query(ServiceStateHistory).filter(
            ServiceStateHistory.service_id.in_(service_ids)
        ).delete(synchronize_session=False)
        session.query(Service).filter(Service.id.in_(service_ids)).delete(synchronize_session=False)
    if user_ids:
        session.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    session.commit()


@pytest.fixture(scope="module")
def world():
    session = SessionLocal()
    try:
        _wipe(session)
        users = {}
        for role, username in USER_BY_ROLE.items():
            user = User(username=username, hashed_password="qa-placeholder", role=role)
            session.add(user)
            session.flush()
            users[role] = user
        session.commit()
        for role, service_name in SERVICE_BY_ROLE.items():
            for env in ENVS:
                session.add(
                    Service(
                        service_name=service_name,
                        environment=env,
                        current_version=1,
                        known_good_version=1,
                        owner_id=users[role].id,
                        status="healthy",
                    )
                )
        session.commit()
        yield
    finally:
        _wipe(session)
        session.close()


@pytest.fixture(autouse=True)
def purge_qa_p_rows():
    def purge():
        session = SessionLocal()
        try:
            session.query(SecurityRequest).filter(
                SecurityRequest.request_id.like("QA-P-%")
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
        self.calls.append((request_id, tool, arguments))
        return McpResponse(200, {"result": {"result": {}}})


def _use_mcp():
    stub = StubMcp()
    app.dependency_overrides[get_mcp_client] = lambda: stub  # conftest removes it
    return stub


def _submit(username, rid, tool, service, env):
    arguments = {"service_name": service, "environment": env}
    if tool == "deploy_service":
        arguments["target_version"] = 2
    payload = {
        "request_id": rid,
        "user_id": username,
        "agent_id": "AG001",
        "tool": tool,
        "arguments": arguments,
    }
    token, _ = issue_token(username)
    return client.post(PATH, json=payload, headers={"Authorization": f"Bearer {token}"})


def _row(db, rid):
    db.expire_all()
    return db.get(SecurityRequest, rid)


def _uid(db, username):
    return db.query(User).filter_by(username=username).one().id


def _blocked(res, stub):
    assert res.status_code == 200
    body = res.json()
    assert body["decision"] == "BLOCK"
    assert stub.calls == []
    return body


# --------------------------------------------------- the 3 x 5 x 2 matrix (#46)
CASES = [
    pytest.param(role, tool, env, i, id=f"{role.value}-{tool}-{env.value}")
    for i, (role, tool, env) in enumerate(product(USER_BY_ROLE, TOOLS, ENVS))
]


@pytest.mark.parametrize("role, tool, env, idx", CASES)
def test_policy_matrix(world, ag001_agent, db, role, tool, env, idx):
    stub = _use_mcp()
    rid = f"QA-P-M{idx:02d}"
    res = _submit(USER_BY_ROLE[role], rid, tool, SERVICE_BY_ROLE[role], env.value)
    key = (role, tool, env)
    assert res.status_code == 200
    body = res.json()
    row = _row(db, rid)
    assert row.user_id == _uid(db, USER_BY_ROLE[role])
    assert row.service_id is not None and row.tool_id is not None and row.environment == env

    if key not in SEED_POLICIES:  # default-deny
        assert body["decision"] == "BLOCK"
        assert body["reason"] == (
            f"Policy stage: role '{role.value}' is not permitted to use '{tool}' in '{env.value}'."
        )
        assert stub.calls == []
        assert row.execution_status == ExecutionStatus.NOT_EXECUTED
    elif SEED_POLICIES[key]:  # approval-bound: fail-closed BLOCK until Phase 11 (#48)
        assert body["decision"] == "BLOCK"
        assert body["reason"] == (
            f"Policy stage: '{tool}' in '{env.value}' requires human approval; the approval "
            "workflow is not implemented yet (Phase 11). Request blocked."
        )
        assert stub.calls == []
        assert row.execution_status == ExecutionStatus.NOT_EXECUTED
    else:  # INTERIM (#48): includes owned production restart/rollback until Phase 9/11
        assert body["decision"] == "ALLOW"
        assert len(stub.calls) == 1
        assert row.decision == Decision.ALLOW
        assert row.execution_status == ExecutionStatus.EXECUTED


# ------------------------------------------------------------- ownership (#47)
def test_non_owner_is_blocked_on_a_write_tool(world, ag001_agent, db):
    stub = _use_mcp()
    # A senior may restart in staging by policy, but does not own the junior's row.
    res = _submit(SENIOR_USER, "QA-P-OWN1", "restart_service", JUNIOR_SVC, "staging")

    body = _blocked(res, stub)
    assert body["reason"] == (
        f"Ownership stage: user '{SENIOR_USER}' is not assigned to '{JUNIOR_SVC}' in 'staging'."
    )
    assert JUNIOR_USER not in body["reason"]  # the owner is never named
    row = _row(db, "QA-P-OWN1")
    assert row.user_id == _uid(db, SENIOR_USER)
    assert row.service_id is not None and row.tool_id is not None
    assert row.environment == Environment.STAGING
    assert row.execution_status == ExecutionStatus.NOT_EXECUTED


@pytest.mark.parametrize(
    "tool, env, rid",
    [
        ("get_logs", "staging", "QA-P-RD1"),
        ("get_logs", "production", "QA-P-RD2"),
        ("get_metrics", "staging", "QA-P-RD3"),
        ("get_metrics", "production", "QA-P-RD4"),
    ],
)
def test_non_owner_is_blocked_on_read_tools_too(world, ag001_agent, db, tool, env, rid):
    stub = _use_mcp()
    # Policy would permit junior reads in both environments; ownership still blocks.
    res = _submit(JUNIOR_USER, rid, tool, SENIOR_SVC, env)

    body = _blocked(res, stub)
    assert body["reason"].startswith(f"Ownership stage: user '{JUNIOR_USER}'")
    assert _row(db, rid).execution_status == ExecutionStatus.NOT_EXECUTED


def test_admin_does_not_bypass_ownership(world, ag001_agent):
    stub = _use_mcp()

    res = _submit(ADMIN_USER, "QA-P-ADM1", "restart_service", JUNIOR_SVC, "staging")

    body = _blocked(res, stub)
    assert body["reason"].startswith(f"Ownership stage: user '{ADMIN_USER}'")


def test_ownership_is_checked_before_policy(world, ag001_agent):
    stub = _use_mcp()
    # Both fail (junior may not deploy, and does not own the senior's row): ownership wins.
    res = _submit(JUNIOR_USER, "QA-P-ORD1", "deploy_service", SENIOR_SVC, "production")

    body = _blocked(res, stub)
    assert body["reason"].startswith("Ownership stage:")


def test_owner_reaches_the_policy_stage_demo_3(world, ag001_agent, db):
    stub = _use_mcp()

    res = _submit(JUNIOR_USER, "QA-P-D3", "deploy_service", JUNIOR_SVC, "staging")

    body = _blocked(res, stub)
    assert body["reason"] == (
        f"Policy stage: role 'junior_developer' is not permitted to use 'deploy_service' "
        "in 'staging'."
    )
    assert _row(db, "QA-P-D3").service_id is not None


# ---------------------------------------------- role comes from the DB (#42, #44)
def test_role_is_read_from_the_database_on_every_request(world, ag001_agent, db):
    stub = _use_mcp()
    denied = _submit(JUNIOR_USER, "QA-P-ROLE1", "deploy_service", JUNIOR_SVC, "staging")
    assert _blocked(denied, stub)["reason"].startswith("Policy stage:")

    db.query(User).filter_by(username=JUNIOR_USER).update({"role": Role.SENIOR_DEVELOPER})
    db.commit()
    try:
        allowed = _submit(JUNIOR_USER, "QA-P-ROLE2", "deploy_service", JUNIOR_SVC, "staging")
    finally:
        db.rollback()
        db.query(User).filter_by(username=JUNIOR_USER).update({"role": Role.JUNIOR_DEVELOPER})
        db.commit()

    assert allowed.json()["decision"] == "ALLOW"  # same kind of token, new DB role
    assert len(stub.calls) == 1


# ------------------------------------------------------ check_policy edge cases
def _tool_id(db, name):
    return db.query(Tool).filter_by(tool_name=name).one().id


def test_conflicting_duplicate_policy_rows_fail_closed(db):
    dup = Policy(
        role=Role.JUNIOR_DEVELOPER,
        tool_id=_tool_id(db, "get_logs"),
        environment=Environment.STAGING,
        action="get_logs",
        allowed=True,
        requires_approval=True,
    )
    db.add(dup)
    db.commit()
    dup_id = dup.id
    try:
        reason = check_policy(db, Role.JUNIOR_DEVELOPER, "get_logs", Environment.STAGING)
    finally:
        db.rollback()
        db.query(Policy).filter_by(id=dup_id).delete()
        db.commit()

    assert reason is not None and "requires human approval" in reason


def test_allowed_false_rows_never_permit(db):
    stray = Policy(
        role=Role.JUNIOR_DEVELOPER,
        tool_id=_tool_id(db, "rollback_deployment"),
        environment=Environment.STAGING,
        action="rollback_deployment",
        allowed=False,
        requires_approval=False,
    )
    db.add(stray)
    db.commit()
    stray_id = stray.id
    try:
        reason = check_policy(db, Role.JUNIOR_DEVELOPER, "rollback_deployment", Environment.STAGING)
    finally:
        db.rollback()
        db.query(Policy).filter_by(id=stray_id).delete()
        db.commit()

    assert reason is not None and "is not permitted" in reason