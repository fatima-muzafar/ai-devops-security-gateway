"""
Rule-based risk engine (Section 10, Section 11 Steps 2-3; decisions.md #53-#59, #62).

Pure and READ-ONLY: assess_risk() only reads `security_requests`; it writes nothing and is
not wired into the pipeline yet (Phase 9 Stage 2 does that). It computes rule_risk_level,
the stubbed ml_risk_level (#59) and final = max(rule, ml).

History is read BEFORE the current request is audited (#35, #56), so a request never
counts itself. Windows are wall-clock on `created_at`; the lower bound is inclusive.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.database.enums import Decision, Environment, ExecutionStatus, RiskLevel, Sensitivity
from app.database.models import SecurityRequest, Tool
from app.gateway import risk_constants as C

# Condition ids recorded in risk_assessments.reasons.
COND_PRODUCTION_MEDIUM = "production_targeting:medium"
COND_PRODUCTION_HIGH = "production_targeting:high"
COND_REQUIRES_APPROVAL = "policy_requires_approval"
COND_REPEATED_DENIALS = "repeated_denials"
COND_S1 = "S1_deploy_then_rollback"
COND_S2 = "S2_consecutive_non_executed_run"
COND_S3 = "S3_identical_destructive_repeat"
MARKER_ML_STUB = "ml=stub"
# #58: final MEDIUM/HIGH is recorded but NOT enforced until Phase 11 (decision is still ALLOW).
MARKER_INTERIM_NOT_ENFORCED = "interim: not enforced"

STATE_CHANGING_TOOLS = frozenset({"restart_service", "rollback_deployment", "deploy_service"})

_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}

# #53/#54: sensitivity matters ONLY together with production targeting; floor MEDIUM.
_PRODUCTION_LEVEL = {
    Sensitivity.LOW: (RiskLevel.MEDIUM, COND_PRODUCTION_MEDIUM),
    Sensitivity.MEDIUM: (RiskLevel.MEDIUM, COND_PRODUCTION_MEDIUM),
    Sensitivity.HIGH: (RiskLevel.HIGH, COND_PRODUCTION_HIGH),
}


@dataclass(frozen=True)
class RiskEvaluation:
    """Named to avoid clashing with the ORM model `RiskAssessment` in Stage 2."""

    rule_risk_level: RiskLevel
    ml_risk_level: RiskLevel
    final_risk_level: RiskLevel
    is_production: bool
    reasons: list


def max_level(*levels: RiskLevel) -> RiskLevel:
    return max(levels, key=_ORDER.__getitem__)


def ml_risk_level_stub() -> RiskLevel:
    """#59: fixed LOW until Phase 14 calibration. No model import."""
    return RiskLevel.LOW


def qualifying_denial_clause(user_id: int):
    """#57: an Ownership/Policy BLOCK of the AUTHENTICATED user.

    Structural filter: BLOCK with user_id, tool_id and service_id all non-null. Given the
    pipeline order (#45, #52) and FK rules (#41, #44) only those two stages match; a test
    checks that against the real pipeline.
    """
    return and_(
        SecurityRequest.user_id == user_id,
        SecurityRequest.decision == Decision.BLOCK,
        SecurityRequest.tool_id.is_not(None),
        SecurityRequest.service_id.is_not(None),
    )


def _failed_allow_clause(user_id: int):
    return and_(
        SecurityRequest.user_id == user_id,
        SecurityRequest.decision == Decision.ALLOW,
        SecurityRequest.execution_status == ExecutionStatus.FAILED,
    )


def count_recent_denials(db: Session, user_id: int, since: datetime) -> int:
    stmt = (
        select(func.count())
        .select_from(SecurityRequest)
        .where(qualifying_denial_clause(user_id), SecurityRequest.created_at >= since)
    )
    return db.execute(stmt).scalar_one()


def _s2_fires(db: Session, user_id: int, since: datetime) -> bool:
    """#62: the user's S2_RUN_LENGTH most recent rows in the window, all qualifying."""
    qualifies = or_(qualifying_denial_clause(user_id), _failed_allow_clause(user_id))
    stmt = (
        select(qualifies)
        .where(SecurityRequest.user_id == user_id, SecurityRequest.created_at >= since)
        .order_by(SecurityRequest.created_at.desc(), SecurityRequest.request_id.desc())
        .limit(C.S2_RUN_LENGTH)
    )
    rows = db.execute(stmt).all()
    return len(rows) == C.S2_RUN_LENGTH and all(r[0] is True for r in rows)


def _executed_count(
    db: Session, user_id: int, service_id: int, tool_name: str, since: datetime
) -> int:
    stmt = (
        select(func.count())
        .select_from(SecurityRequest)
        .join(Tool, Tool.id == SecurityRequest.tool_id)
        .where(
            SecurityRequest.user_id == user_id,
            SecurityRequest.service_id == service_id,
            Tool.tool_name == tool_name,
            SecurityRequest.decision == Decision.ALLOW,
            SecurityRequest.execution_status == ExecutionStatus.EXECUTED,
            SecurityRequest.created_at >= since,
        )
    )
    return db.execute(stmt).scalar_one()


def assess_risk(
    db: Session,
    *,
    user_id: int,
    tool_name: str,
    sensitivity: Sensitivity,
    environment: Environment,
    service_id: int,
    requires_approval: bool = False,
    now: datetime | None = None,
) -> RiskEvaluation:
    now = now or datetime.now(timezone.utc)
    is_production = environment is Environment.PRODUCTION
    ml = ml_risk_level_stub()

    # #53: reads are LOW and exempt from every condition (no history queries at all).
    if tool_name not in STATE_CHANGING_TOOLS:
        return RiskEvaluation(
            RiskLevel.LOW, ml, max_level(RiskLevel.LOW, ml), is_production, [MARKER_ML_STUB]
        )

    levels: list[RiskLevel] = [RiskLevel.LOW]  # owned, permitted staging change = LOW
    reasons: list[str] = []

    if is_production:
        level, cond = _PRODUCTION_LEVEL[sensitivity]
        levels.append(level)
        reasons.append(cond)

    if requires_approval:  # recorded for Phase 11; unreachable in Phase 9 (#48)
        levels.append(RiskLevel.HIGH)
        reasons.append(COND_REQUIRES_APPROVAL)

    if count_recent_denials(db, user_id, now - C.DENIAL_WINDOW) >= C.DENIAL_THRESHOLD:
        levels.append(RiskLevel.MEDIUM)
        reasons.append(COND_REPEATED_DENIALS)

    if _s2_fires(db, user_id, now - C.S2_WINDOW):
        levels.append(RiskLevel.HIGH)
        reasons.append(COND_S2)

    if tool_name == "rollback_deployment" and (
        _executed_count(db, user_id, service_id, "deploy_service", now - C.S1_WINDOW) > 0
    ):
        levels.append(RiskLevel.MEDIUM)
        reasons.append(COND_S1)

    if _executed_count(db, user_id, service_id, tool_name, now - C.S3_WINDOW) >= C.S3_PRIOR_EXECUTED:
        levels.append(RiskLevel.MEDIUM)
        reasons.append(COND_S3)

    rule = max_level(*levels)
    return RiskEvaluation(
        rule, ml, max_level(rule, ml), is_production, reasons + [MARKER_ML_STUB]
    )