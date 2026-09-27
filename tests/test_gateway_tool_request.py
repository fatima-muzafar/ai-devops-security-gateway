"""
Phase 5: end-to-end test for POST /api/gateway/tool-request.

Verifies the full request -> placeholder decision -> execute_tool ->
service_state_history pipeline, using STATUS.md's corrected verification
method: assert a new service_state_history row exists, not a status
diff. A freshly created test service is already "healthy" (Section 13
seed state), so a restart leaves `status` unchanged either way -- a
status diff would prove nothing.

Uses the real `db` / `test_service` fixtures from tests/conftest.py.
The endpoint resolves its own DB session via app.database.base.get_db
(a separate SQLAlchemy session/connection from the test's `db` fixture),
so assertions re-query through `db` after each request to read back
whatever the endpoint committed.
"""
from fastapi.testclient import TestClient

from app.database.enums import ChangeType
from app.database.models import ServiceStateHistory
from app.main import app

client = TestClient(app)


def _history_count(db, service_id, change_type=None):
    query = db.query(ServiceStateHistory).filter_by(service_id=service_id)
    if change_type is not None:
        query = query.filter_by(change_type=change_type)
    return query.count()


def test_restart_service_staging_allows_and_records_history(db, test_service):
    """environment=staging -> placeholder rule ALLOWs -> execute_tool runs
    restart_service -> a new service_state_history row is created
    (Scenario B / Demo 2's ALLOW path, exercised over HTTP for the first
    time in Phase 5)."""
    before = _history_count(db, test_service.id, ChangeType.RESTART)

    response = client.post(
        "/api/gateway/tool-request",
        json={
            "request_id": "REQ-TEST-001",
            "user_id": "qa_test_owner",
            "tool": "restart_service",
            "arguments": {
                "service_name": test_service.service_name,
                "environment": "staging",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "ALLOW"
    assert body["result"]["result"]["change_type"] == "restart"

    after = _history_count(db, test_service.id, ChangeType.RESTART)
    assert after == before + 1


def test_restart_service_production_blocks_before_mcp(db, test_service):
    """environment=production -> placeholder rule BLOCKs -> execute_tool is
    never called -> no service_state_history row is created (Section 5/11:
    BLOCK means no MCP call, no state change).

    test_service only exists in staging; that's fine here -- the
    placeholder rule decides purely from the request's own `environment`
    field before touching the database, so a matching production Service
    row is not needed to prove the BLOCK path never reaches MCP.
    """
    before = _history_count(db, test_service.id)

    response = client.post(
        "/api/gateway/tool-request",
        json={
            "request_id": "REQ-TEST-002",
            "user_id": "qa_test_owner",
            "tool": "restart_service",
            "arguments": {
                "service_name": test_service.service_name,
                "environment": "production",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "BLOCK"
    assert "result" not in body

    after = _history_count(db, test_service.id)
    assert after == before


def test_unknown_tool_returns_400_not_a_security_decision(db, test_service):
    """A dispatch failure (unregistered tool) is a 400, not ALLOW/BLOCK --
    decisions.md #11: MCP dispatch errors are a separate error taxonomy
    from the Gateway's ALLOW/BLOCK/APPROVAL_REQUIRED decisions."""
    response = client.post(
        "/api/gateway/tool-request",
        json={
            "request_id": "REQ-TEST-003",
            "user_id": "qa_test_owner",
            "tool": "delete_everything",
            "arguments": {
                "service_name": test_service.service_name,
                "environment": "staging",
            },
        },
    )

    assert response.status_code == 400