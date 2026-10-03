"""
Phase 5 tests, updated in Phase 7 Stage 3 (decisions.md #33, #34, #41).

Changes from Phase 5, all deliberate:
- every request now carries agent_id "AG001" (the Gateway requires it);
- the production test uses `test_service_production`, because the service stage
  now runs BEFORE the placeholder policy stage;
- the old "unknown tool -> HTTP 400" test is replaced: an unknown tool is a
  BLOCK decision (HTTP 200) and is audited.

The endpoint uses its own DB session, so assertions re-query after expiring the
test session's identity map.
"""
from fastapi.testclient import TestClient

from app.database.enums import ChangeType, Decision, ExecutionStatus
from app.database.models import SecurityRequest, ServiceStateHistory
from app.main import app

client = TestClient(app)
PATH = "/api/gateway/tool-request"


def _history_count(db, service_id, change_type=None):
    query = db.query(ServiceStateHistory).filter_by(service_id=service_id)
    if change_type is not None:
        query = query.filter_by(change_type=change_type)
    return query.count()


def _audit_row(db, request_id):
    db.expire_all()
    return db.get(SecurityRequest, request_id)


def _payload(request_id, service_name, environment, tool="restart_service"):
    return {
        "request_id": request_id,
        "user_id": "qa_test_owner",
        "agent_id": "AG001",
        "tool": tool,
        "arguments": {"service_name": service_name, "environment": environment},
    }


def test_restart_service_staging_allows_and_records_history(db, test_service):
    """staging -> ALLOW -> MCP runs restart_service -> one new
    service_state_history row (Scenario B / Demo 2)."""
    before = _history_count(db, test_service.id, ChangeType.RESTART)

    response = client.post(
        PATH, json=_payload("REQ-TEST-001", test_service.service_name, "staging")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "ALLOW"
    assert body["result"]["result"]["change_type"] == "restart"
    assert _history_count(db, test_service.id, ChangeType.RESTART) == before + 1


def test_restart_service_production_blocks_before_mcp(db, test_service, test_service_production):
    """production (service exists) -> placeholder policy BLOCK -> MCP never
    called -> no history row (Section 5/11)."""
    before = _history_count(db, test_service_production.id)

    response = client.post(
        PATH, json=_payload("REQ-TEST-002", test_service.service_name, "production")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "BLOCK"
    assert body["reason"].startswith("Phase 5 placeholder rule")
    assert "result" not in body
    assert _history_count(db, test_service_production.id) == before


def test_unknown_tool_is_blocked_and_audited(db, test_service):
    """Replaces the Phase 5 'unknown tool -> HTTP 400' test (decisions.md #34):
    an unregistered tool is a Section 11 Step 1 BLOCK, HTTP 200, with an audit row."""
    response = client.post(
        PATH,
        json=_payload("REQ-TEST-003", test_service.service_name, "staging", tool="delete_everything"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "BLOCK"
    assert "Tool registry stage" in body["reason"]

    row = _audit_row(db, "REQ-TEST-003")
    assert row is not None
    assert row.decision == Decision.BLOCK
    assert row.tool_id is None
    assert row.user_id is not None
    assert row.reason == body["reason"]
    assert row.execution_status == ExecutionStatus.NOT_EXECUTED