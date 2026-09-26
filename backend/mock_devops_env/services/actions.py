"""
Phase 3: mock DevOps environment — state-mutation logic.

These are plain Python functions operating on the ORM `Service` model.
They are NOT MCP tools and NOT Gateway-facing endpoints — Phase 4 wires
them behind MCP tool definitions, and Phase 7+ puts the Security Gateway
in front of that. Do not call these from an API route yet; that wiring
is out of Phase 3's scope (STATUS.md Phase 3 Boundary).

Every function here assumes the caller has already decided the action is
permitted. Phase 3 has no auth/policy/risk logic at all. In the finished
system, only an ALLOW decision, or an APPROVAL_REQUIRED request that has
passed TOCTOU revalidation, ever reaches this layer (Section 11).

Each mutation writes exactly one row to service_state_history
(decisions.md #7) in the same transaction as the state change it
records, so the two can never disagree.
"""
from sqlalchemy.orm import Session

from app.database.enums import ChangeType
from app.database.models import Service, ServiceStateHistory


def restart_service(db: Session, service: Service) -> ServiceStateHistory:
    """restart_service(): Medium sensitivity (Section 12). Updates
    restart/status metadata only — never touches version."""
    status_before = service.status
    service.status = "healthy"  # mock effect: a restart always recovers to healthy

    history = ServiceStateHistory(
        service_id=service.id,
        change_type=ChangeType.RESTART,
        version_before=None,
        version_after=None,
        status_before=status_before,
        status_after=service.status,
    )
    db.add(history)
    db.flush()
    return history


def rollback_deployment(db: Session, service: Service) -> ServiceStateHistory:
    """rollback_deployment(): Medium-High sensitivity (Section 12).
    Changes current_version to known_good_version. Does NOT itself
    change known_good_version — see the design-gap note in the reply
    this file shipped with; unconfirmed pending your sign-off."""
    version_before = service.current_version
    status_before = service.status

    service.current_version = service.known_good_version
    service.status = "healthy"

    history = ServiceStateHistory(
        service_id=service.id,
        change_type=ChangeType.ROLLBACK,
        version_before=version_before,
        version_after=service.current_version,
        status_before=status_before,
        status_after=service.status,
    )
    db.add(history)
    db.flush()
    return history


def deploy_service(db: Session, service: Service, target_version: int) -> ServiceStateHistory:
    """deploy_service(): High sensitivity (Section 12). Changes
    deployed/current version and records the deployment.

    UNCONFIRMED DESIGN CHOICE (flagged, not in decisions.md yet): this
    also sets known_good_version = the version being replaced, so a
    later rollback reverts to "whatever was running immediately before
    this deploy" (standard CI/CD "last known stable" semantics), rather
    than always reverting to v1. Section 12/13 of the planning doc never
    specifies this. Change or remove this line if you want option (a)
    instead — "known_good_version never updates after seed."
    """
    if target_version <= 0:
        raise ValueError(
            "target_version must be a positive integer "
            "(Section 13: monotonically increasing integer counters)"
        )

    version_before = service.current_version
    status_before = service.status

    service.known_good_version = service.current_version  # see UNCONFIRMED note above
    service.current_version = target_version
    service.status = "healthy"

    history = ServiceStateHistory(
        service_id=service.id,
        change_type=ChangeType.DEPLOY,
        version_before=version_before,
        version_after=service.current_version,
        status_before=status_before,
        status_after=service.status,
    )
    db.add(history)
    db.flush()
    return history