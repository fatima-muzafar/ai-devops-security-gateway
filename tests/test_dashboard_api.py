"""
Phase 12 Stage 1: dashboard read endpoints and CORS (decisions.md #90-#101).

GET /api/security/events and GET /api/mock/services are admin only, read only and never return
raw_request, arguments, tokens or password hashes. Test rows use request ids "QA-DASH-..." and
created_at in the year 2099, so they are the NEWEST rows in the shared dev DB (#101) and no test
depends on what else is in it. Every fixture tears down through qa_cleanup.delete_requests().
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.database.enums import ApprovalStatus, Decision, Environment, ExecutionStatus, RiskLevel, Role
from app.database.models import (
    ApprovalRequest, BehaviorEvent, RiskAssessment, SecurityRequest, Service, Tool, User,
)
from app.gateway.decision import APPROVAL_REASON
from app.main import CORS_ORIGINS, _cors_origins, app
from qa_cleanup import delete_requests

EVENTS, SERVICES = "/api/security/events", "/api/mock/services"
BOTH = [EVENTS, SERVICES]
STAGING, PRODUCTION = Environment.STAGING, Environment.PRODUCTION

PREFIX = "QA-DASH-"
LEAK = "QA-DASH-RAW-LEAK-MARKER"
BASE = datetime(2099, 1, 1, tzinfo=timezone.utc)

ID_ALLOW, ID_BLOCK, ID_AUTH = PREFIX + "ALLOW", PREFIX + "BLOCK", PREFIX + "AUTH"
ID_APPROVAL, ID_NULL = PREFIX + "APPROVAL", PREFIX + "NULL"
ORDER = [ID_ALLOW, ID_BLOCK, ID_AUTH, ID_APPROVAL, ID_NULL]  # newest first
MINUTES = {ID_ALLOW: 5, ID_BLOCK: 4, ID_AUTH: 3, ID_APPROVAL: 2, ID_NULL: 1}

EVENT_KEYS = {
    "request_id", "created_at", "requester", "agent", "service_name", "environment", "tool",
    "decision", "reason", "execution_status", "risk", "approval_status",
}
SERVICE_KEYS = {
    "service_name", "environment", "current_version", "known_good_version", "status", "owner",
}
SEEDED = {  # decisions.md #8
    ("auth-service", "staging"): "senior_developer_1",
    ("auth-service", "production"): "admin",
    ("payment-service", "staging"): "senior_developer_2",
    ("payment-service", "production"): "admin",
    ("notification-service", "staging"): "junior_developer_1",
    ("notification-service", "production"): "senior_developer_1",
}

client = TestClient(app)


# ---------------------------------------------------------------- helpers

def _add_request(db, rid, minutes, *, user=None, agent=None, service=None, tool=None, env=None,
                 decision=None, reason=None, status=ExecutionStatus.NOT_EXECUTED):
    row = SecurityRequest(
        request_id=rid,
        user_id=user.id if user else None,
        agent_id=agent.id if agent else None,
        service_id=service.id if service else None,
        environment=env,
        tool_id=tool.id if tool else None,
        arguments={"marker": LEAK},
        raw_request={"marker": LEAK},
        decision=decision,
        reason=reason,
        execution_status=status,
        created_at=BASE + timedelta(minutes=minutes),
    )
    db.add(row)
    db.flush()
    return row


def _wipe(db):
    db.rollback()
    delete_requests(db, SecurityRequest.request_id.like(PREFIX + "%"))
    db.commit()


def _get_events(headers, **params):
    return client.get(EVENTS, params=params, headers=headers)


def _mine(body):
    return [e for e in body if e["request_id"].startswith(PREFIX)]


@pytest.fixture
def dash(db, make_user, ag001_agent, test_service, test_service_production, auth_headers):
    """Five known events (ALLOW, Ownership BLOCK, Authentication BLOCK, APPROVAL_REQUIRED with a
    pending approval, NULL decision) plus an admin token. Newest first: ALLOW ... NULL."""
    _wipe(db)
    senior = make_user("qa_dash_senior", Role.SENIOR_DEVELOPER)
    junior = make_user("qa_dash_junior", Role.JUNIOR_DEVELOPER)
    make_user("qa_dash_admin", Role.ADMIN)
    restart = db.query(Tool).filter_by(tool_name="restart_service").one()
    deploy = db.query(Tool).filter_by(tool_name="deploy_service").one()
    stg, prod = test_service, test_service_production

    _add_request(db, ID_ALLOW, 5, user=senior, agent=ag001_agent, service=stg, tool=restart,
                 env=STAGING, decision=Decision.ALLOW, status=ExecutionStatus.EXECUTED)
    db.add(RiskAssessment(
        request_id=ID_ALLOW, rule_risk_level=RiskLevel.LOW, ml_risk_level=RiskLevel.LOW,
        final_risk_level=RiskLevel.LOW, decision=Decision.ALLOW, reasons=["ml=stub"],
        is_production=False,
    ))
    _add_request(db, ID_BLOCK, 4, user=junior, agent=ag001_agent, service=stg, tool=restart,
                 env=STAGING, decision=Decision.BLOCK,
                 reason="Ownership stage: user 'qa_dash_junior' is not assigned to "
                        "'qa-test-service' in 'staging'.")
    _add_request(db, ID_AUTH, 3, decision=Decision.BLOCK,
                 reason="Authentication stage: missing bearer token.")
    _add_request(db, ID_APPROVAL, 2, user=senior, agent=ag001_agent, service=prod, tool=deploy,
                 env=PRODUCTION, decision=Decision.APPROVAL_REQUIRED, reason=APPROVAL_REASON)
    db.add(RiskAssessment(
        request_id=ID_APPROVAL, rule_risk_level=RiskLevel.HIGH, ml_risk_level=RiskLevel.LOW,
        final_risk_level=RiskLevel.HIGH, decision=Decision.APPROVAL_REQUIRED,
        reasons=["requires_approval", "ml=stub"], is_production=True,
    ))
    db.add(ApprovalRequest(
        request_id=ID_APPROVAL, status=ApprovalStatus.PENDING,
        state_snapshot={"current_version": 1, "known_good_version": 1},
    ))
    _add_request(db, ID_NULL, 1, user=senior, agent=ag001_agent, service=stg, tool=restart,
                 env=STAGING)
    db.commit()

    yield SimpleNamespace(
        headers=auth_headers("qa_dash_admin"), agent_name=ag001_agent.agent_name,
    )

    _wipe(db)


def _event(dash, rid):
    r = _get_events(dash.headers, limit=200)
    assert r.status_code == 200
    found = [e for e in r.json() if e["request_id"] == rid]
    assert len(found) == 1
    return found[0]


def _assert_event(event, expected):
    """Exact comparison; created_at is compared as a moment (the DB may add its own UTC offset)."""
    assert set(event) == EVENT_KEYS
    created = event.pop("created_at")
    assert datetime.fromisoformat(created) == BASE + timedelta(minutes=MINUTES[event["request_id"]])
    assert event == expected


# ---------------------------------------------------------------- authentication / role (#91)

@pytest.mark.parametrize("path", BOTH)
def test_no_token_is_401(path):
    r = client.get(path)
    assert r.status_code == 401
    assert r.json() == {"detail": "Not authenticated."}


@pytest.mark.parametrize("path", BOTH)
@pytest.mark.parametrize("header", ["Basic dXNlcjpwYXNz", "Bearer not-a-real-token"])
def test_wrong_scheme_or_garbage_token_is_401(path, header):
    r = client.get(path, headers={"Authorization": header})
    assert r.status_code == 401
    assert r.json() == {"detail": "Not authenticated."}


@pytest.mark.parametrize("path", BOTH)
def test_valid_token_for_unknown_user_is_401(path, auth_headers):
    r = client.get(path, headers=auth_headers("qa_dash_ghost_user"))
    assert r.status_code == 401
    assert r.json() == {"detail": "Not authenticated."}


@pytest.mark.parametrize("path", BOTH)
@pytest.mark.parametrize("role", [Role.JUNIOR_DEVELOPER, Role.SENIOR_DEVELOPER])
def test_non_admin_is_403(path, role, make_user, auth_headers):
    name = f"qa_dash_nonadmin_{role.value}"
    make_user(name, role)
    r = client.get(path, headers=auth_headers(name))
    assert r.status_code == 403
    assert r.json() == {"detail": "Forbidden."}


@pytest.mark.parametrize("path", BOTH)
def test_unconfigured_jwt_secret_is_503(path, make_user, auth_headers, monkeypatch):
    make_user("qa_dash_cfg", Role.ADMIN)
    headers = auth_headers("qa_dash_cfg")
    monkeypatch.delenv("JWT_SECRET")
    r = client.get(path, headers=headers)
    assert r.status_code == 503
    assert r.json() == {"detail": "Authentication is not configured."}


@pytest.mark.parametrize("path", BOTH)
def test_role_is_read_from_the_db_not_the_token(path, db, make_user, auth_headers):
    make_user("qa_dash_rolechange", Role.JUNIOR_DEVELOPER)
    headers = auth_headers("qa_dash_rolechange")  # the SAME token is used three times
    assert client.get(path, headers=headers).status_code == 403
    db.query(User).filter_by(username="qa_dash_rolechange").update({"role": Role.ADMIN})
    db.commit()
    assert client.get(path, headers=headers).status_code == 200
    db.query(User).filter_by(username="qa_dash_rolechange").update({"role": Role.JUNIOR_DEVELOPER})
    db.commit()
    assert client.get(path, headers=headers).status_code == 403


# ---------------------------------------------------------------- events: exact rows (#92)

def test_event_allow_row_is_exact(dash):
    _assert_event(_event(dash, ID_ALLOW), {
        "request_id": ID_ALLOW, "requester": "qa_dash_senior", "agent": dash.agent_name,
        "service_name": "qa-test-service", "environment": "staging", "tool": "restart_service",
        "decision": "ALLOW", "reason": None, "execution_status": "executed",
        "risk": {
            "rule_risk_level": "LOW", "ml_risk_level": "LOW", "final_risk_level": "LOW",
            "reasons": ["ml=stub"],
        },
        "approval_status": None,
    })


def test_event_block_row_has_no_risk(dash):
    _assert_event(_event(dash, ID_BLOCK), {
        "request_id": ID_BLOCK, "requester": "qa_dash_junior", "agent": dash.agent_name,
        "service_name": "qa-test-service", "environment": "staging", "tool": "restart_service",
        "decision": "BLOCK",
        "reason": "Ownership stage: user 'qa_dash_junior' is not assigned to "
                  "'qa-test-service' in 'staging'.",
        "execution_status": "not_executed", "risk": None, "approval_status": None,
    })


def test_event_auth_failure_row_has_null_requester(dash):
    _assert_event(_event(dash, ID_AUTH), {
        "request_id": ID_AUTH, "requester": None, "agent": None, "service_name": None,
        "environment": None, "tool": None, "decision": "BLOCK",
        "reason": "Authentication stage: missing bearer token.",
        "execution_status": "not_executed", "risk": None, "approval_status": None,
    })


def test_event_approval_required_row_shows_risk_and_pending_approval(dash):
    _assert_event(_event(dash, ID_APPROVAL), {
        "request_id": ID_APPROVAL, "requester": "qa_dash_senior", "agent": dash.agent_name,
        "service_name": "qa-test-service", "environment": "production", "tool": "deploy_service",
        "decision": "APPROVAL_REQUIRED", "reason": APPROVAL_REASON,
        "execution_status": "not_executed",
        "risk": {
            "rule_risk_level": "HIGH", "ml_risk_level": "LOW", "final_risk_level": "HIGH",
            "reasons": ["requires_approval", "ml=stub"],
        },
        "approval_status": "pending",
    })


def test_event_with_null_decision_is_listed_with_null(dash):
    _assert_event(_event(dash, ID_NULL), {
        "request_id": ID_NULL, "requester": "qa_dash_senior", "agent": dash.agent_name,
        "service_name": "qa-test-service", "environment": "staging", "tool": "restart_service",
        "decision": None, "reason": None, "execution_status": "not_executed",
        "risk": None, "approval_status": None,
    })


# ---------------------------------------------------------------- events: order, limit, filter (#93)

def test_events_are_newest_first(dash):
    body = _get_events(dash.headers, limit=200).json()
    assert [e["request_id"] for e in body[:5]] == ORDER


def test_ties_are_broken_by_request_id_descending(db, dash):
    _add_request(db, PREFIX + "TIE-A", 100, decision=Decision.BLOCK, reason="tie a")
    _add_request(db, PREFIX + "TIE-B", 100, decision=Decision.BLOCK, reason="tie b")
    db.commit()
    body = _get_events(dash.headers, limit=200).json()
    assert [e["request_id"] for e in body[:3]] == [PREFIX + "TIE-B", PREFIX + "TIE-A", ID_ALLOW]


def test_default_limit_is_50(db, dash):
    for i in range(55):  # makes sure the table holds more than 50 rows
        _add_request(db, f"{PREFIX}F{i:02d}", 200, decision=Decision.BLOCK, reason="filler")
    db.commit()
    r = client.get(EVENTS, headers=dash.headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 50
    assert body[0]["request_id"] == PREFIX + "F54"


def test_limit_is_applied(dash):
    body = _get_events(dash.headers, limit=2).json()
    assert [e["request_id"] for e in body] == [ID_ALLOW, ID_BLOCK]


@pytest.mark.parametrize("limit", ["0", "-1", "201", "abc"])
def test_limit_out_of_range_is_422(dash, limit):
    r = _get_events(dash.headers, limit=limit)
    assert r.status_code == 422


@pytest.mark.parametrize("value, expected", [
    ("ALLOW", [ID_ALLOW]),
    ("BLOCK", [ID_BLOCK, ID_AUTH]),
    ("APPROVAL_REQUIRED", [ID_APPROVAL]),
])
def test_decision_filter(dash, value, expected):
    body = _get_events(dash.headers, decision=value, limit=200).json()
    assert all(e["decision"] == value for e in body)
    assert [e["request_id"] for e in _mine(body)] == expected


@pytest.mark.parametrize("value", ["bogus", "allow"])
def test_decision_filter_rejects_unknown_values(dash, value):
    r = _get_events(dash.headers, decision=value)
    assert r.status_code == 422


# ---------------------------------------------------------------- events: safety (#92, #93)

def test_events_never_leak_secrets(dash):
    r = _get_events(dash.headers, limit=200)
    assert r.status_code == 200
    token = dash.headers["Authorization"].split(" ", 1)[1]
    for item in r.json():
        assert set(item) == EVENT_KEYS  # so no raw_request / arguments key can exist
    for forbidden in (LEAK, "hashed_password", "$argon2", token):
        assert forbidden not in r.text


def test_each_request_appears_exactly_once(dash):
    ids = [e["request_id"] for e in _mine(_get_events(dash.headers, limit=200).json())]
    assert sorted(ids) == sorted(ORDER)


def test_dashboard_endpoints_write_nothing(db, dash):
    def counts():
        db.rollback()
        models = (SecurityRequest, RiskAssessment, ApprovalRequest, BehaviorEvent, Service)
        return tuple(db.query(m).count() for m in models)

    before = counts()
    assert _get_events(dash.headers, limit=200).status_code == 200
    assert client.get(SERVICES, headers=dash.headers).status_code == 200
    assert counts() == before


# ---------------------------------------------------------------- mock services (#94)

@pytest.fixture
def svc_rows(db, make_user, auth_headers):
    owner = make_user("qa_dash_svc_owner", Role.SENIOR_DEVELOPER)
    make_user("qa_dash_svc_admin", Role.ADMIN)
    rows = [
        Service(service_name="qa-dash-b", environment=STAGING, current_version=3,
                known_good_version=2, owner_id=owner.id, status="healthy"),
        Service(service_name="qa-dash-a", environment=PRODUCTION, current_version=1,
                known_good_version=1, owner_id=owner.id, status="degraded"),
        Service(service_name="qa-dash-a", environment=STAGING, current_version=5,
                known_good_version=4, owner_id=owner.id, status="healthy"),
    ]
    db.add_all(rows)
    db.commit()
    ids = [row.id for row in rows]

    yield SimpleNamespace(headers=auth_headers("qa_dash_svc_admin"))

    db.rollback()
    db.query(Service).filter(Service.id.in_(ids)).delete(synchronize_session=False)
    db.commit()


def test_services_rows_are_exact_and_ordered(svc_rows):
    r = client.get(SERVICES, headers=svc_rows.headers)
    assert r.status_code == 200
    mine = [s for s in r.json() if s["service_name"].startswith("qa-dash-")]
    assert mine == [
        {"service_name": "qa-dash-a", "environment": "production", "current_version": 1,
         "known_good_version": 1, "status": "degraded", "owner": "qa_dash_svc_owner"},
        {"service_name": "qa-dash-a", "environment": "staging", "current_version": 5,
         "known_good_version": 4, "status": "healthy", "owner": "qa_dash_svc_owner"},
        {"service_name": "qa-dash-b", "environment": "staging", "current_version": 3,
         "known_good_version": 2, "status": "healthy", "owner": "qa_dash_svc_owner"},
    ]


def test_seeded_six_services_are_present_with_their_owners(make_user, auth_headers):
    make_user("qa_dash_seedreader", Role.ADMIN)
    body = client.get(SERVICES, headers=auth_headers("qa_dash_seedreader")).json()
    got = {
        (s["service_name"], s["environment"]): s["owner"]
        for s in body if (s["service_name"], s["environment"]) in SEEDED
    }
    assert got == SEEDED
    for s in body:
        assert set(s) == SERVICE_KEYS
        assert isinstance(s["current_version"], int) and isinstance(s["known_good_version"], int)


def test_services_never_leak_secrets(svc_rows):
    r = client.get(SERVICES, headers=svc_rows.headers)
    token = svc_rows.headers["Authorization"].split(" ", 1)[1]
    for item in r.json():
        assert set(item) == SERVICE_KEYS  # no owner_id, no password hash
    for forbidden in ("hashed_password", "$argon2", token):
        assert forbidden not in r.text


# ---------------------------------------------------------------- CORS (#96, #101)

def _preflight(origin, method="GET"):
    return client.options(EVENTS, headers={
        "Origin": origin,
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": "authorization",
    })


def test_cors_preflight_for_an_allowed_origin():
    origin = CORS_ORIGINS[0]
    r = _preflight(origin)
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == origin
    assert "authorization" in r.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in r.headers


def test_cors_refuses_an_unknown_origin():
    r = _preflight("http://evil.example")
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers
    plain = client.get(SERVICES, headers={"Origin": "http://evil.example"})
    assert plain.status_code == 401
    assert "access-control-allow-origin" not in plain.headers


def test_cors_refuses_a_method_that_is_not_allowed():
    r = _preflight(CORS_ORIGINS[0], method="DELETE")
    assert r.status_code == 400


def test_cors_headers_are_present_on_an_error_response():
    origin = CORS_ORIGINS[0]
    r = client.get(SERVICES, headers={"Origin": origin})  # no token: 401
    assert r.status_code == 401
    assert r.headers["access-control-allow-origin"] == origin


def test_cors_origins_default(monkeypatch):
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    assert _cors_origins() == ["http://localhost:3000"]


def test_cors_origins_list_is_trimmed(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", " http://localhost:3000/ , http://127.0.0.1:3000 ,, ")
    assert _cors_origins() == ["http://localhost:3000", "http://127.0.0.1:3000"]


@pytest.mark.parametrize("raw, expected", [
    ("*", ["http://localhost:3000"]),
    ("*,http://a.example", ["http://a.example"]),
])
def test_cors_wildcard_is_dropped(monkeypatch, raw, expected):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", raw)
    assert _cors_origins() == expected
