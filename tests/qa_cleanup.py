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
