"""
Phase 7 Stage 2: the internal MCP seam, POST /mcp/tools/execute
(decisions.md #37, #40) and McpClient.

Tokens are generated per test with secrets.token_hex and set via monkeypatch;
no real token is ever hardcoded. Uses the real `db` / `test_service` fixtures.
"""
import secrets

import pytest
from fastapi.testclient import TestClient

from app.database.enums import ChangeType
from app.database.models import ServiceStateHistory
from app.gateway.mcp_client import McpClient, McpUnavailableError
from app.main import app

client = TestClient(app)

PATH = "/mcp/tools/execute"
TOKEN_ENV = "MCP_INTERNAL_TOKEN"
HEADER = "X-Internal-Token"
FORBIDDEN_BODY = {"detail": "Forbidden."}


@pytest.fixture
def mcp_token(monkeypatch):
    token = secrets.token_hex(16)
    monkeypatch.setenv(TOKEN_ENV, token)
    return token


def _history_count(db, service_id, change_type=None):
    query = db.query(ServiceStateHistory).filter_by(service_id=service_id)
    if change_type is not None:
        query = query.filter_by(change_type=change_type)
    return query.count()


def _body(test_service, tool="restart_service", **extra_args):
    return {
        "request_id": "QA-S2-001",
        "tool": tool,
        "arguments": {
            "service_name": test_service.service_name,
            "environment": "staging",
            **extra_args,
        },
    }


# ------------------------------------------------------------ rejected (403)
def test_missing_token_is_rejected_and_nothing_executes(db, test_service, mcp_token):
    before = _history_count(db, test_service.id)

    res = client.post(PATH, json=_body(test_service))

    assert res.status_code == 403
    assert res.json() == FORBIDDEN_BODY
    assert _history_count(db, test_service.id) == before


def test_wrong_token_is_rejected_with_same_generic_body(db, test_service, mcp_token):
    before = _history_count(db, test_service.id)

    res = client.post(PATH, json=_body(test_service), headers={HEADER: mcp_token + "x"})

    assert res.status_code == 403
    assert res.json() == FORBIDDEN_BODY
    assert _history_count(db, test_service.id) == before


@pytest.mark.parametrize(
    "headers",
    [{HEADER: "anything"}, {HEADER: ""}, {}],
    ids=["any-token", "empty-token", "no-header"],
)
def test_env_var_unset_rejects_everything(db, test_service, monkeypatch, headers):
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    before = _history_count(db, test_service.id)

    res = client.post(PATH, json=_body(test_service), headers=headers)

    assert res.status_code == 403
    assert res.json() == FORBIDDEN_BODY
    assert _history_count(db, test_service.id) == before


def test_env_var_empty_does_not_match_empty_header(db, test_service, monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "")
    before = _history_count(db, test_service.id)

    res = client.post(PATH, json=_body(test_service), headers={HEADER: ""})

    assert res.status_code == 403
    assert res.json() == FORBIDDEN_BODY
    assert _history_count(db, test_service.id) == before


# --------------------------------------------------------------- valid token
def test_valid_token_restart_staging_executes_once(db, test_service, mcp_token):
    before = _history_count(db, test_service.id, ChangeType.RESTART)

    res = client.post(PATH, json=_body(test_service), headers={HEADER: mcp_token})

    assert res.status_code == 200
    assert res.json()["result"]["result"]["change_type"] == "restart"
    assert _history_count(db, test_service.id, ChangeType.RESTART) == before + 1


def test_valid_token_get_logs_is_read_only(db, test_service, mcp_token):
    before = _history_count(db, test_service.id)

    res = client.post(
        PATH, json=_body(test_service, tool="get_logs"), headers={HEADER: mcp_token}
    )

    assert res.status_code == 200
    assert "result" in res.json()
    assert _history_count(db, test_service.id) == before


def test_unknown_tool_is_400_not_a_decision(db, test_service, mcp_token):
    res = client.post(
        PATH,
        json=_body(test_service, tool="delete_everything"),
        headers={HEADER: mcp_token},
    )

    assert res.status_code == 400
    assert "decision" not in res.json()


def test_invalid_tool_arguments_are_422_and_do_not_execute(db, test_service, mcp_token):
    before = _history_count(db, test_service.id)

    res = client.post(
        PATH,
        json=_body(test_service, tool="deploy_service", target_version=0),
        headers={HEADER: mcp_token},
    )

    assert res.status_code == 422
    assert _history_count(db, test_service.id) == before


def test_missing_environment_is_422(db, test_service, mcp_token):
    body = _body(test_service)
    del body["arguments"]["environment"]

    res = client.post(PATH, json=body, headers={HEADER: mcp_token})

    assert res.status_code == 422


def test_reserved_argument_key_is_422_not_500(db, test_service, mcp_token):
    before = _history_count(db, test_service.id)

    res = client.post(
        PATH, json=_body(test_service, tool_name="x"), headers={HEADER: mcp_token}
    )

    assert res.status_code == 422
    assert _history_count(db, test_service.id) == before


# ----------------------------------------------------------------- McpClient
def test_mcp_client_round_trip_with_explicit_token(db, test_service, mcp_token):
    mcp = McpClient(TestClient(app), token=mcp_token)
    before = _history_count(db, test_service.id, ChangeType.RESTART)

    res = mcp.execute(
        "QA-S2-CLIENT-1",
        "restart_service",
        {"service_name": test_service.service_name, "environment": "staging"},
    )

    assert res.status_code == 200
    assert res.body["result"]["result"]["change_type"] == "restart"
    assert _history_count(db, test_service.id, ChangeType.RESTART) == before + 1


def test_mcp_client_reads_token_from_env_at_call_time(db, test_service, monkeypatch):
    mcp = McpClient(TestClient(app))  # built BEFORE the env var exists
    monkeypatch.setenv(TOKEN_ENV, secrets.token_hex(16))

    res = mcp.execute(
        "QA-S2-CLIENT-2",
        "get_logs",
        {"service_name": test_service.service_name, "environment": "staging"},
    )

    assert res.status_code == 200


def test_mcp_client_wrong_token_returns_403_response(db, test_service, mcp_token):
    mcp = McpClient(TestClient(app), token=mcp_token + "x")
    before = _history_count(db, test_service.id)

    res = mcp.execute(
        "QA-S2-CLIENT-3",
        "restart_service",
        {"service_name": test_service.service_name, "environment": "staging"},
    )

    assert res.status_code == 403
    assert res.body == FORBIDDEN_BODY
    assert _history_count(db, test_service.id) == before


def test_mcp_client_without_any_token_refuses_to_call(test_service, monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    mcp = McpClient(TestClient(app))

    with pytest.raises(McpUnavailableError):
        mcp.execute(
            "QA-S2-CLIENT-4",
            "restart_service",
            {"service_name": test_service.service_name, "environment": "staging"},
        )