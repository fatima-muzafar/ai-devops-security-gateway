"""
Stage 1 (decisions.md #32, #39): verifies the security_requests schema can
audit an unresolved request, and that the execution_status CHECK exists.
Rows use the QA-S1- prefix and are removed after each test.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database.enums import Decision, ExecutionStatus
from app.database.models import SecurityRequest


@pytest.fixture
def cleanup_audit_rows(db):
    yield
    db.rollback()
    db.query(SecurityRequest).filter(
        SecurityRequest.request_id.like("QA-S1-%")
    ).delete(synchronize_session=False)
    db.commit()


def test_unresolved_block_row_can_be_stored(db, cleanup_audit_rows):
    db.add(
        SecurityRequest(
            request_id="QA-S1-AUDIT-001",
            user_id=None,
            agent_id=None,
            service_id=None,
            tool_id=None,
            environment=None,
            arguments={},
            raw_request={"user_id": "ghost", "tool": "delete_everything"},
            decision=Decision.BLOCK,
            reason="unknown user",
        )
    )
    db.commit()
    db.expire_all()

    saved = db.get(SecurityRequest, "QA-S1-AUDIT-001")
    assert saved.user_id is None and saved.agent_id is None
    assert saved.service_id is None and saved.tool_id is None
    assert saved.environment is None
    assert saved.raw_request["tool"] == "delete_everything"
    assert saved.reason == "unknown user"
    assert saved.execution_status == ExecutionStatus.NOT_EXECUTED


def test_execution_status_check_constraint_rejects_unknown_value(db, cleanup_audit_rows):
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO security_requests "
                "(request_id, arguments, raw_request, execution_status) "
                "VALUES ('QA-S1-BAD-001', '{}', '{}', 'bogus')"
            )
        )
    db.rollback()