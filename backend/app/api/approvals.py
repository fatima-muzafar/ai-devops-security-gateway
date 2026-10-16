"""
Approval endpoints (Section 14/17; decisions.md #82, #83, #89). Thin: auth -> app.approvals.

MUST stay sync `def` (#26, #37): approving calls MCP over HTTP inside the same process.
Every endpoint is admin only. The role is read from the DB (#44), never from the token.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, aliased

from app.api.deps import Caller, require_caller
from app.approvals import service as approvals
from app.approvals.execution import ApprovalExecutionFailedError, finish_decision
from app.database.base import get_db
from app.database.enums import ApprovalStatus, Role
from app.database.models import (
    Agent, ApprovalRequest, RiskAssessment, SecurityRequest, Service, Tool, User,
)
from app.gateway.mcp_client import get_mcp_client

router = APIRouter()


class DecisionIn(BaseModel):
    reason: str | None = None


def require_admin(
    caller: Caller = Depends(require_caller), db: Session = Depends(get_db)
) -> User:
    user = db.query(User).filter_by(username=caller.username).one_or_none()
    if user is None:
        raise HTTPException(
            status_code=401, detail="Not authenticated.", headers={"WWW-Authenticate": "Bearer"}
        )
    if user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Forbidden.")
    return user


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


@router.get("/api/approvals")
def list_approvals(
    status: ApprovalStatus = ApprovalStatus.PENDING,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    requester, reviewer = aliased(User), aliased(User)
    rows = (
        db.query(ApprovalRequest, SecurityRequest, RiskAssessment, requester, reviewer, Agent, Service, Tool)
        .join(SecurityRequest, SecurityRequest.request_id == ApprovalRequest.request_id)
        .outerjoin(RiskAssessment, RiskAssessment.request_id == SecurityRequest.request_id)
        .outerjoin(requester, requester.id == SecurityRequest.user_id)
        .outerjoin(reviewer, reviewer.id == ApprovalRequest.reviewer_id)
        .outerjoin(Agent, Agent.id == SecurityRequest.agent_id)
        .outerjoin(Service, Service.id == SecurityRequest.service_id)
        .outerjoin(Tool, Tool.id == SecurityRequest.tool_id)
        .filter(ApprovalRequest.status == status)
        .order_by(ApprovalRequest.created_at, ApprovalRequest.id)
        .all()
    )
    return [
        {
            "id": appr.id,
            "request_id": appr.request_id,
            "status": appr.status.value,
            "created_at": _iso(appr.created_at),
            "decided_at": _iso(appr.decided_at),
            "reviewer": rev.username if rev else None,
            "reason": appr.reason,
            "revalidation": appr.revalidation,
            "requester": req_user.username if req_user else None,
            "agent": agent.agent_name if agent else None,
            "service_name": svc.service_name if svc else None,
            "environment": sec.environment.value if sec.environment else None,
            "tool": tool.tool_name if tool else None,
            "arguments": sec.arguments,
            "risk": (
                {
                    "rule_risk_level": risk.rule_risk_level.value,
                    "ml_risk_level": risk.ml_risk_level.value,
                    "final_risk_level": risk.final_risk_level.value,
                    "reasons": risk.reasons,
                }
                if risk
                else None
            ),
        }
        for appr, sec, risk, req_user, rev, agent, svc, tool in rows
    ]


def _decide(db: Session, mcp_client, approval_id: int, admin: User, *, approve: bool, reason):
    try:
        outcome = approvals.process_decision(db, approval_id, admin, approve=approve, reason=reason)
    except approvals.ApprovalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except approvals.ReasonRequiredError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (approvals.NotAdminError, approvals.SelfApprovalError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except approvals.AlreadyDecidedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        done = finish_decision(db, mcp_client, outcome)
    except ApprovalExecutionFailedError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    body: dict[str, Any] = {
        "approval_id": outcome.approval.id,
        "request_id": outcome.approval.request_id,
        "approval_status": outcome.approval.status.value,
        "outcome": done.outcome,
    }
    if done.outcome == "revalidation_failed":
        body["reason"] = done.reason
    if done.outcome == "executed":
        body["result"] = done.result
    return body


@router.post("/api/approvals/{approval_id}/approve")
def approve(
    approval_id: int,
    body: DecisionIn | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    mcp_client=Depends(get_mcp_client),
):
    return _decide(db, mcp_client, approval_id, admin, approve=True, reason=body.reason if body else None)


@router.post("/api/approvals/{approval_id}/reject")
def reject(
    approval_id: int,
    body: DecisionIn | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    mcp_client=Depends(get_mcp_client),
):
    return _decide(db, mcp_client, approval_id, admin, approve=False, reason=body.reason if body else None)
