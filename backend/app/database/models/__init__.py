"""
Import every model here. Alembic's autogenerate (and anything else that
inspects Base.metadata) only sees tables whose model class has actually
been imported somewhere. If you add an 11th table later and forget to
add it here, autogenerate will silently skip it - no error, just a
missing migration.
"""
from app.database.models.users import User
from app.database.models.agents import Agent
from app.database.models.services import Service
from app.database.models.tools import Tool
from app.database.models.policies import Policy
from app.database.models.security_requests import SecurityRequest
from app.database.models.risk_assessments import RiskAssessment
from app.database.models.approval_requests import ApprovalRequest
from app.database.models.behavior_events import BehaviorEvent
from app.database.models.incidents import Incident

__all__ = [
    "User",
    "Agent",
    "Service",
    "Tool",
    "Policy",
    "SecurityRequest",
    "RiskAssessment",
    "ApprovalRequest",
    "BehaviorEvent",
    "Incident",
]
