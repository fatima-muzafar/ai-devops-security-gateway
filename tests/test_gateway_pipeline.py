"""
Phase 7 Stage 3: the Gateway pipeline, audit rows, duplicate handling and MCP
failure handling (decisions.md #34-#36, #41).

All request_ids start with QA-S3- so rows whose FKs are all NULL (unknown user,
etc.) can be purged by prefix; rows with FKs are also removed by the fixtures.
"""
import pytest
from fastapi.testclient import TestClient

from app.database.base import SessionLocal
from app.database.enums import ChangeType, Decision, Environment, ExecutionStatus
from app.database.models import SecurityRequest, ServiceStateHistory, Tool
from app.gateway.mcp_client import McpClient, McpResponse, McpUnavailableError, get_mcp_client
from app.main import app

client = TestClient(app)
PATH = "/api/gateway/tool-request"
USER = "qa_test_owner"
SERVICE = "qa-test-service"
PLACEHOLDER_REASON = (
    "Phase 5 placeholder rule: production is blocked "
    "unconditionally (not real policy -- see Phase 8)."
)


@pytest.fixture(autouse=True)
def purge_qa_s3_rows():
    def purge():
        session = SessionLocal()
        try:
            session.query(SecurityRequest).filter(
                SecurityRequest.request_id.like("QA-S3-%")
            ).delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()

    purge()
    yield
    purge()


class StubMcpClient:
    """Records calls; returns a canned response or raises."""

    def __init__(self, response=None, exc=None):
        self.calls = []
        self._response = response or McpResponse(200, {"result": {"result": {"stub": True}}})
        self._exc = exc

    def execute(self, request_id, tool, arguments):
        self.calls.append((request_id, tool, arguments))
        if self._exc is not None:
            raise self._exc
        return self._response


def _use_mcp(client_obj):
    # The autouse conftest fixture removes this override at teardown.
    app.dependency_overrides[get_mcp_client] = lambda: client_obj
    return client_obj


def _payload(request_id, **overrides):
    payload = {
        "request_id": request_id,
        "user_id": USER,
        "agent_id": "AG001",
        "tool": "restart_service",
        "arguments": {"service_name": SERVICE, "environment": "staging"},
    }
    payload.update(overrides)
    return payload


def _row(db, request_id):
    db.expire_all()
    return db.get(SecurityRequest, request_id)


def _history_count(db, service_id, change_type=None):
    query = db.query(ServiceStateHistory).filter_by(service_id=service_id)
    if change_type is not None:
        query = query.filter_by(change_type=change_type)
    return query.count()


# ------------------------------------------------------------------ ALLOW
def test_allow_is_audited_as_executed_and_changes_state(db, test_service):
    before = _history_count(db, test_service.id, ChangeType.RESTART)

    res = client.post(PATH, json=_payload("QA-S3-ALLOW-1"))

    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"request_id", "decision", "result"}  # no risk_level (#38)
    assert body["decision"] == "ALLOW"
    assert body["result"]["result"]["change_type"] == "restart"  # nesting unchanged

    row = _row(db, "QA-S3-ALLOW-1")
    assert row.decision == Decision.ALLOW
    assert row.execution_status == ExecutionStatus.EXECUTED
    assert row.reason is None
    assert row.user_id is not None and row.agent_id is not None and row.tool_id is not None
    assert row.service_id == test_service.id
    assert row.environment == Environment.STAGING
    assert _history_count(db, test_service.id, ChangeType.RESTART) == before + 1


def test_audit_row_is_committed_before_mcp_is_called(db, test_service):
    seen = {}

    class ProbeClient:
        def execute(self, request_id, tool, arguments):
            session = SessionLocal()  # independent connection: sees only COMMITTED rows
            try:
                row = session.get(SecurityRequest, request_id)
                seen["status"] = row.execution_status if row else "missing"
                seen["decision"] = row.decision if row else None
            finally:
                session.close()
            return McpResponse(200, {"result": {"result": {}}})

    _use_mcp(ProbeClient())

    res = client.post(PATH, json=_payload("QA-S3-PROBE-1"))

    assert res.status_code == 200
    assert seen == {"status": ExecutionStatus.NOT_EXECUTED, "decision": Decision.ALLOW}
    assert _row(db, "QA-S3-PROBE-1").execution_status == ExecutionStatus.EXECUTED


# ------------------------------------------------------------------ BLOCK
_NONE = dict(user=False, agent=False, tool=False, service=False, env=None)
BLOCK_CASES = [
    pytest.param({"user_id": "qa_no_such_user"}, _NONE, "Identity stage", id="unknown-user"),
    pytest.param(
        {"agent_id": "QA-NO-SUCH-AGENT"},
        dict(user=True, agent=False, tool=False, service=False, env=None),
        "Identity stage",
        id="unknown-agent",
    ),
    pytest.param(
        {"agent_id": None},
        dict(user=True, agent=False, tool=False, service=False, env=None),
        "Identity stage",
        id="missing-agent",
    ),
    pytest.param(
        {"tool": "delete_everything"},
        dict(user=True, agent=True, tool=False, service=False, env=None),
        "Tool registry stage",
        id="unregistered-tool",
    ),
    pytest.param(
        {"arguments": {"environment": "staging"}},
        dict(user=True, agent=True, tool=True, service=False, env="staging"),
        "Arguments stage",
        id="missing-service-name",
    ),
    pytest.param(
        {"arguments": {"service_name": SERVICE, "environment": "qa-moon"}},
        dict(user=True, agent=True, tool=True, service=False, env=None),
        "Arguments stage",
        id="invalid-environment",
    ),
    pytest.param(
        {
            "tool": "deploy_service",
            "arguments": {"service_name": SERVICE, "environment": "staging", "target_version": 0},
        },
        dict(user=True, agent=True, tool=True, service=False, env="staging"),
        "Arguments stage",
        id="schema-invalid",
    ),
    pytest.param(
        {"arguments": {"service_name": SERVICE, "environment": "staging", "tool_name": "x"}},
        dict(user=True, agent=True, tool=True, service=False, env="staging"),
        "reserved",
        id="reserved-key",
    ),
    pytest.param(
        {"arguments": {"service_name": "qa-no-such-service", "environment": "staging"}},
        dict(user=True, agent=True, tool=True, service=False, env="staging"),
        "Service stage",
        id="unknown-service",
    ),
]


@pytest.mark.parametrize("overrides, resolved, fragment", BLOCK_CASES)
def test_block_is_audited_with_correct_nulls_and_makes_no_mcp_call(
    db, test_service, request, overrides, resolved, fragment
):
    stub = _use_mcp(StubMcpClient())
    rid = f"QA-S3-B-{request.node.callspec.id}"
    payload = _payload(rid, **overrides)
    before = _history_count(db, test_service.id)

    res = client.post(PATH, json=payload)

    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"request_id", "decision", "reason"}
    assert body["decision"] == "BLOCK"
    assert fragment in body["reason"]
    assert stub.calls == []  # BLOCK never reaches MCP
    assert _history_count(db, test_service.id) == before

    row = _row(db, rid)
    assert row is not None
    assert row.decision == Decision.BLOCK
    assert row.reason == body["reason"] and row.reason
    assert row.execution_status == ExecutionStatus.NOT_EXECUTED
    assert (row.user_id is not None) is resolved["user"]
    assert (row.agent_id is not None) is resolved["agent"]
    assert (row.tool_id is not None) is resolved["tool"]
    assert (row.service_id is not None) is resolved["service"]
    assert row.environment == resolved["env"]
    assert row.raw_request == payload
    assert row.arguments == payload["arguments"]


def test_disabled_tool_is_blocked_and_audited(db, test_service):
    stub = _use_mcp(StubMcpClient())
    tool = db.query(Tool).filter_by(tool_name="get_metrics").one()
    original = tool.enabled
    tool.enabled = False
    db.commit()
    try:
        res = client.post(PATH, json=_payload("QA-S3-B-disabled-tool", tool="get_metrics"))
    finally:
        db.rollback()
        db.query(Tool).filter_by(tool_name="get_metrics").update({"enabled": original})
        db.commit()

    assert res.status_code == 200
    body = res.json()
    assert body["decision"] == "BLOCK"
    assert "disabled" in body["reason"]
    assert stub.calls == []
    row = _row(db, "QA-S3-B-disabled-tool")
    assert row.tool_id is not None  # the tool row resolved; it is just disabled
    assert row.service_id is None
    assert row.execution_status == ExecutionStatus.NOT_EXECUTED


def test_production_placeholder_blocks_with_unchanged_reason(db, test_service, test_service_production):
    stub = _use_mcp(StubMcpClient())
    payload = _payload(
        "QA-S3-B-production",
        arguments={"service_name": SERVICE, "environment": "production"},
    )

    res = client.post(PATH, json=payload)

    assert res.status_code == 200
    body = res.json()
    assert body["decision"] == "BLOCK"
    assert body["reason"] == PLACEHOLDER_REASON
    assert stub.calls == []
    row = _row(db, "QA-S3-B-production")
    assert row.service_id == test_service_production.id
    assert row.environment == Environment.PRODUCTION
    assert row.user_id is not None and row.agent_id is not None and row.tool_id is not None
    assert _history_count(db, test_service_production.id) == 0


# ------------------------------------------------------ request_id rules (#36)
def test_duplicate_request_id_is_409_and_does_not_execute_twice(db, test_service):
    first = client.post(PATH, json=_payload("QA-S3-DUP-1"))
    assert first.status_code == 200
    original = _row(db, "QA-S3-DUP-1")
    original_created = original.created_at
    before = _history_count(db, test_service.id, ChangeType.RESTART)

    second = client.post(PATH, json=_payload("QA-S3-DUP-1"))

    assert second.status_code == 409
    assert "detail" in second.json()
    assert _history_count(db, test_service.id, ChangeType.RESTART) == before  # no 2nd execution
    after = _row(db, "QA-S3-DUP-1")
    assert after.decision == Decision.ALLOW
    assert after.execution_status == ExecutionStatus.EXECUTED
    assert after.created_at == original_created


def test_replaying_a_blocked_id_with_a_valid_request_is_409_and_stays_blocked(db, test_service):
    blocked = client.post(PATH, json=_payload("QA-S3-DUP-2", tool="delete_everything"))
    assert blocked.json()["decision"] == "BLOCK"
    before = _history_count(db, test_service.id)

    replay = client.post(PATH, json=_payload("QA-S3-DUP-2"))  # now a valid request

    assert replay.status_code == 409
    assert _history_count(db, test_service.id) == before
    row = _row(db, "QA-S3-DUP-2")
    assert row.decision == Decision.BLOCK
    assert row.execution_status == ExecutionStatus.NOT_EXECUTED


def test_request_id_longer_than_32_chars_is_422_and_not_audited(db, test_service):
    long_id = "QA-S3-" + "x" * 27  # 33 chars
    assert len(long_id) == 33

    res = client.post(PATH, json=_payload(long_id))

    assert res.status_code == 422
    assert _row(db, long_id[:32]) is None


def test_request_id_of_exactly_32_chars_is_accepted(db, test_service):
    rid = "QA-S3-" + "y" * 26  # 32 chars
    assert len(rid) == 32
    _use_mcp(StubMcpClient())

    res = client.post(PATH, json=_payload(rid, tool="delete_everything"))

    assert res.status_code == 200
    assert _row(db, rid) is not None


# -------------------------------------------------- MCP failure -> 502 (#34)
def test_mcp_non_200_is_502_and_recorded_as_failed(db, test_service):
    _use_mcp(StubMcpClient(McpResponse(500, {"detail": "boom"})))

    res = client.post(PATH, json=_payload("QA-S3-FAIL-1"))

    assert res.status_code == 502
    body = res.json()
    assert "HTTP 500" in body["detail"]
    assert "decision" not in body and "result" not in body  # never a 200 ALLOW
    row = _row(db, "QA-S3-FAIL-1")
    assert row.decision == Decision.ALLOW
    assert row.execution_status == ExecutionStatus.FAILED


def test_mcp_unavailable_is_502_and_recorded_as_failed(db, test_service):
    _use_mcp(StubMcpClient(exc=McpUnavailableError("down")))

    res = client.post(PATH, json=_payload("QA-S3-FAIL-2"))

    assert res.status_code == 502
    assert "unavailable" in res.json()["detail"].lower()
    row = _row(db, "QA-S3-FAIL-2")
    assert row.decision == Decision.ALLOW
    assert row.execution_status == ExecutionStatus.FAILED


def test_wrong_internal_token_fails_closed_end_to_end(db, test_service):
    """FR-15 on the real Gateway path: MCP rejects the call (403), the Gateway
    reports 502, the row is `failed`, and nothing executed."""
    _use_mcp(McpClient(TestClient(app), token="qa-not-the-real-token"))
    before = _history_count(db, test_service.id)

    res = client.post(PATH, json=_payload("QA-S3-FAIL-3"))

    assert res.status_code == 502
    assert "HTTP 403" in res.json()["detail"]
    assert _row(db, "QA-S3-FAIL-3").execution_status == ExecutionStatus.FAILED
    assert _history_count(db, test_service.id) == before