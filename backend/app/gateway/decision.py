"""
Section 11 Step 4 decision mapping (decisions.md #78). Pure: no DB, no I/O.

Step 1 hard failures never reach this function (they are BLOCKs earlier). There is no
BLOCK-class yet: which HIGH production actions become BLOCK is a Phase 15 policy choice, and
production rollback must never be one of them (#54).
"""
from app.database.enums import Decision, RiskLevel


def decide_from_risk(final_risk: RiskLevel, requires_approval: bool) -> Decision:
    """Policy-mandated approval wins; then LOW -> ALLOW, MEDIUM/HIGH -> APPROVAL_REQUIRED."""
    if requires_approval:
        return Decision.APPROVAL_REQUIRED
    if final_risk == RiskLevel.LOW:
        return Decision.ALLOW
    return Decision.APPROVAL_REQUIRED
