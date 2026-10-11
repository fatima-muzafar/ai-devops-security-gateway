"""
Test cleanup helper (decisions.md #58): risk_assessments.request_id is a FK to
security_requests, so every teardown that deletes audit rows must delete their risk rows
first. Route ALL audit-row deletes in tests through delete_requests().
"""
from sqlalchemy import select

from app.database.models import RiskAssessment, SecurityRequest


def delete_requests(session, *criteria) -> int:
    ids = select(SecurityRequest.request_id).where(*criteria)
    session.query(RiskAssessment).filter(RiskAssessment.request_id.in_(ids)).delete(
        synchronize_session=False
    )
    return session.query(SecurityRequest).filter(*criteria).delete(synchronize_session=False)


def delete_behavior_events(session, *criteria) -> int:
    """Phase 10 (decisions.md #75): behavior_events FK-reference users, services, agents,
    tools and (live rows) security_requests. A test that creates events must delete them
    BEFORE deleting those parents. Stage 2 also makes delete_requests() remove live events."""
    from app.database.models import BehaviorEvent

    return session.query(BehaviorEvent).filter(*criteria).delete(synchronize_session=False)
