"""
Approval workflow logic (Section 14; decisions.md #82-#84). No HTTP, no MCP: Stage 2 adds
the router and the MCP call on top of process_decision().

create_pending() only ADDS the row (the Gateway commits it with the audit rows, #80).
decide() commits the human decision at once, as ONE atomic UPDATE ... WHERE status='pending'.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.database.enums import ApprovalStatus, Role
from app.database.models import ApprovalRequest, SecurityRequest, User
from app.gateway.revalidation import RevalidationResult, revalidate_approval


class ApprovalError(Exception):
    """Base class. The router maps subclasses to HTTP codes (#83)."""


class ApprovalNotFoundError(ApprovalError):          # 404
    pass


class NotAdminError(ApprovalError):                  # 403
    pass


class SelfApprovalError(ApprovalError):              # 403
    pass


class ReasonRequiredError(ApprovalError):            # 422
    pass


class AlreadyDecidedError(ApprovalError):            # 409
    pass


@dataclass(frozen=True)
class ApprovalOutcome:
    approval: ApprovalRequest
    revalidation: RevalidationResult | None  # None when rejected (never run, #84)


def create_pending(db: Session, request_id: str, snapshot: dict[str, int]) -> ApprovalRequest:
    row = ApprovalRequest(
        request_id=request_id, status=ApprovalStatus.PENDING, state_snapshot=dict(snapshot)
    )
    db.add(row)
    return row


def decide(
    db: Session,
    approval_id: int,
    reviewer: User,
    *,
    approve: bool,
    reason: str | None,
    now: datetime | None = None,
) -> ApprovalRequest:
    """Record the human decision. Check order: admin -> exists -> reason -> self-approval ->
    atomic update. Self-approval is forbidden, self-rejection is allowed (#82)."""
    if reviewer.role != Role.ADMIN:
        raise NotAdminError("only an admin can decide approvals.")
    approval = db.get(ApprovalRequest, approval_id)
    if approval is None:
        raise ApprovalNotFoundError(f"approval {approval_id} not found.")
    if not approve and not (reason and reason.strip()):
        raise ReasonRequiredError("a reason is required to reject.")
    if approve:
        sec = db.get(SecurityRequest, approval.request_id)
        if sec is not None and sec.user_id == reviewer.id:
            raise SelfApprovalError("a reviewer cannot approve their own request.")

    result = db.execute(
        update(ApprovalRequest)
        .where(ApprovalRequest.id == approval_id, ApprovalRequest.status == ApprovalStatus.PENDING)
        .values(
            status=ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED,
            reviewer_id=reviewer.id,
            reason=reason,
            decided_at=now or datetime.now(timezone.utc),
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise AlreadyDecidedError(f"approval {approval_id} is already decided.")
    db.commit()
    db.refresh(approval)
    return approval


def record_revalidation(db: Session, approval_id: int, result: RevalidationResult) -> None:
    db.execute(
        update(ApprovalRequest)
        .where(ApprovalRequest.id == approval_id)
        .values(revalidation=result.stored_text)
        .execution_options(synchronize_session=False)
    )
    db.commit()


def process_decision(
    db: Session,
    approval_id: int,
    reviewer: User,
    *,
    approve: bool,
    reason: str | None,
    revalidate_fn: Callable[[Session, ApprovalRequest], RevalidationResult] = revalidate_approval,
) -> ApprovalOutcome:
    """decide(); then, ONLY if approved, revalidate and store the result. A rejected request
    never reaches revalidation (#84). Stage 2 calls MCP when the result is ok."""
    approval = decide(db, approval_id, reviewer, approve=approve, reason=reason)
    if not approve:
        return ApprovalOutcome(approval, None)
    result = revalidate_fn(db, approval)
    record_revalidation(db, approval.id, result)
    db.refresh(approval)
    return ApprovalOutcome(approval, result)
