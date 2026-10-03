"""
PHASE 8 PLACEHOLDER (decisions.md #31, #41).

This is the Phase 5 rule, relocated unchanged: BLOCK if production. It is NOT
Section 8's policy engine: no role, no ownership, no `policies` table. Phase 8
replaces this module's logic entirely; it does not extend it.
"""
from app.database.enums import Environment

PLACEHOLDER_PRODUCTION_REASON = (
    "Phase 5 placeholder rule: production is blocked "
    "unconditionally (not real policy -- see Phase 8)."
)


def evaluate_placeholder_policy(environment: Environment) -> str | None:
    """Return a BLOCK reason, or None to allow."""
    if environment == Environment.PRODUCTION:
        return PLACEHOLDER_PRODUCTION_REASON
    return None