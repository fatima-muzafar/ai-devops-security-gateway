"""
Audit persistence (decisions.md #35, #36, #41, #58, #80): exactly ONE security_requests
INSERT per request, for requests that passed every Step 1 stage ONE risk_assessments
INSERT, and for APPROVAL_REQUIRED ONE approval_requests INSERT -- all in the SAME commit,
BEFORE any MCP call; then, on ALLOW only, one UPDATE of execution_status.

A failed risk write rolls the audit row back too (HTTP 500, MCP not called, no trace of
the request). Accepted limitation (#58): it fails closed.
"""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.approvals.service import create_pending
from app.database.enums import Decision, ExecutionStatus
from app.database.models import RiskAssessment, SecurityRequest


class DuplicateRequestError(Exception):
    """request_id already exists (#36). The original row is untouched."""


def _build_risk_row(req, verdict) -> RiskAssessment:
    """#58/#78: decision = the ENACTED decision. Since Phase 11 risk is enforced, so the
    "interim: not enforced" marker is no longer written (old rows keep it)."""
    risk = verdict.risk
    reasons = list(risk.reasons)
    return RiskAssessment(
        request_id=req.request_id,
        rule_risk_level=risk.rule_risk_level,
        ml_risk_level=risk.ml_risk_level,
        final_risk_level=risk.final_risk_level,
        decision=verdict.decision,
        reasons=reasons,
        is_production=risk.is_production,
    )


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
        if verdict.risk is not None:
            db.add(_build_risk_row(req, verdict))
        if verdict.decision is Decision.APPROVAL_REQUIRED:
            create_pending(db, req.request_id, verdict.state_snapshot)
        db.commit()
    except IntegrityError:
        db.rollback()
        # Only call it a duplicate if the row really exists; any other
        # integrity failure is a bug and must not be misreported.
        if db.get(SecurityRequest, req.request_id) is not None:
            raise DuplicateRequestError(req.request_id)
        raise
    except Exception:
        db.rollback()  # #58: a failed risk write also removes the audit row (fails closed)
        raise


def mark_execution(db: Session, request_id: str, status: ExecutionStatus) -> None:
    row = db.get(SecurityRequest, request_id)
    row.execution_status = status
    db.commit()