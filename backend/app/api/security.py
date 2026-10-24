"""
Security events endpoint for the dashboard (Section 17, FR-19; decisions.md #91-#93, #101).

READ ONLY: no insert, no update, no behavior event. Admin only; the role is read from the DB
(require_admin, #44). The query selects COLUMNS, never the whole SecurityRequest row, so
raw_request and arguments are not even loaded (#92). Risk detail is shown to an admin only
(#79); it must never be added to a Gateway response (#60).

Keep this route sync `def` like the other routes (#26, #37).
"""
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, aliased

from app.api.approvals import require_admin
from app.database.base import get_db
from app.database.enums import Decision
from app.database.models import (
    Agent, ApprovalRequest, RiskAssessment, SecurityRequest, Service, Tool, User,
)

router = APIRouter()

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _risk(risk: RiskAssessment | None) -> dict[str, Any] | None:
    if risk is None:
        return None
    return {
        "rule_risk_level": risk.rule_risk_level.value,
        "ml_risk_level": risk.ml_risk_level.value,
        "final_risk_level": risk.final_risk_level.value,
        "reasons": risk.reasons,
    }


@router.get("/api/security/events")
def list_events(
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    decision: Decision | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    requester = aliased(User)
    query = (
        db.query(
            SecurityRequest.request_id,
            SecurityRequest.created_at,
            SecurityRequest.environment,
            SecurityRequest.decision,
            SecurityRequest.reason,
            SecurityRequest.execution_status,
            requester.username,
            Agent.agent_name,
            Service.service_name,
            Tool.tool_name,
            RiskAssessment,
            ApprovalRequest.status,
        )
        .select_from(SecurityRequest)
        .outerjoin(requester, requester.id == SecurityRequest.user_id)
        .outerjoin(Agent, Agent.id == SecurityRequest.agent_id)
        .outerjoin(Service, Service.id == SecurityRequest.service_id)
        .outerjoin(Tool, Tool.id == SecurityRequest.tool_id)
        .outerjoin(RiskAssessment, RiskAssessment.request_id == SecurityRequest.request_id)
        .outerjoin(ApprovalRequest, ApprovalRequest.request_id == SecurityRequest.request_id)
    )
    if decision is not None:
        query = query.filter(SecurityRequest.decision == decision)
    rows = (
        query.order_by(SecurityRequest.created_at.desc(), SecurityRequest.request_id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "request_id": request_id,
            "created_at": created_at.isoformat() if created_at is not None else None,
            "requester": requester_name,
            "agent": agent_name,
            "service_name": service_name,
            "environment": environment.value if environment is not None else None,
            "tool": tool_name,
            "decision": req_decision.value if req_decision is not None else None,
            "reason": reason,
            "execution_status": execution_status.value,
            "risk": _risk(risk),
            "approval_status": approval_status.value if approval_status is not None else None,
        }
        for (
            request_id, created_at, environment, req_decision, reason, execution_status,
            requester_name, agent_name, service_name, tool_name, risk, approval_status,
        ) in rows
    ]
