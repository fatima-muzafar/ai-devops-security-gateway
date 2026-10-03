"""
Audit persistence (decisions.md #35, #36, #41): exactly ONE security_requests
INSERT per request, committed BEFORE any MCP call; then, on ALLOW only, one
UPDATE of execution_status.
"""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.enums import ExecutionStatus
from app.database.models import SecurityRequest


class DuplicateRequestError(Exception):
    """request_id already exists (#36). The original row is untouched."""


def record_decision(db: Session, req, verdict) -> None:
    db.add(
        SecurityRequest(
            request_id=req.request_id,
            user_id=verdict.user_id,
            agent_id=verdict.agent_id,
            service_id=verdict.service_id,
            environment=verdict.environment,
            tool_id=verdict.tool_id,
            arguments=req.arguments,
            raw_request=req.raw_request,
            decision=verdict.decision,
            reason=verdict.reason,
            execution_status=ExecutionStatus.NOT_EXECUTED,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Only call it a duplicate if the row really exists; any other
        # integrity failure is a bug and must not be misreported.
        if db.get(SecurityRequest, req.request_id) is not None:
            raise DuplicateRequestError(req.request_id)
        raise


def mark_execution(db: Session, request_id: str, status: ExecutionStatus) -> None:
    row = db.get(SecurityRequest, request_id)
    row.execution_status = status
    db.commit()