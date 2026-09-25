"""add missing enum check constraints

Revision ID: 6b86e1e35917
Revises: 0b6eff3ade85
Create Date: 2026-09-25 15:52:53.502000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b86e1e35917'
down_revision: Union[str, Sequence[str], None] = '0b6eff3ade85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Hand-written: Alembic autogenerate does not detect
    new CHECK constraints on existing columns, so this could not be
    generated automatically."""
    op.create_check_constraint('ck_users_role', 'users', "role IN ('junior_developer', 'senior_developer', 'admin')")
    op.create_check_constraint('ck_services_environment', 'services', "environment IN ('staging', 'production')")
    op.create_check_constraint('ck_tools_sensitivity', 'tools', "sensitivity IN ('low', 'medium', 'high')")
    op.create_check_constraint('ck_policies_role', 'policies', "role IN ('junior_developer', 'senior_developer', 'admin')")
    op.create_check_constraint('ck_policies_environment', 'policies', "environment IN ('staging', 'production')")
    op.create_check_constraint('ck_security_requests_environment', 'security_requests', "environment IN ('staging', 'production')")
    op.create_check_constraint('ck_security_requests_decision', 'security_requests', "decision IN ('ALLOW', 'BLOCK', 'APPROVAL_REQUIRED')")
    op.create_check_constraint('ck_risk_assessments_rule_risk_level', 'risk_assessments', "rule_risk_level IN ('LOW', 'MEDIUM', 'HIGH')")
    op.create_check_constraint('ck_risk_assessments_ml_risk_level', 'risk_assessments', "ml_risk_level IN ('LOW', 'MEDIUM', 'HIGH')")
    op.create_check_constraint('ck_risk_assessments_final_risk_level', 'risk_assessments', "final_risk_level IN ('LOW', 'MEDIUM', 'HIGH')")
    op.create_check_constraint('ck_risk_assessments_decision', 'risk_assessments', "decision IN ('ALLOW', 'BLOCK', 'APPROVAL_REQUIRED')")
    op.create_check_constraint('ck_approval_requests_status', 'approval_requests', "status IN ('pending', 'approved', 'rejected')")
    op.create_check_constraint('ck_behavior_events_environment', 'behavior_events', "environment IN ('staging', 'production')")
    op.create_check_constraint('ck_behavior_events_outcome', 'behavior_events', "outcome IN ('allowed', 'blocked', 'pending')")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_behavior_events_outcome', 'behavior_events', type_='check')
    op.drop_constraint('ck_behavior_events_environment', 'behavior_events', type_='check')
    op.drop_constraint('ck_approval_requests_status', 'approval_requests', type_='check')
    op.drop_constraint('ck_risk_assessments_decision', 'risk_assessments', type_='check')
    op.drop_constraint('ck_risk_assessments_final_risk_level', 'risk_assessments', type_='check')
    op.drop_constraint('ck_risk_assessments_ml_risk_level', 'risk_assessments', type_='check')
    op.drop_constraint('ck_risk_assessments_rule_risk_level', 'risk_assessments', type_='check')
    op.drop_constraint('ck_security_requests_decision', 'security_requests', type_='check')
    op.drop_constraint('ck_security_requests_environment', 'security_requests', type_='check')
    op.drop_constraint('ck_policies_environment', 'policies', type_='check')
    op.drop_constraint('ck_policies_role', 'policies', type_='check')
    op.drop_constraint('ck_tools_sensitivity', 'tools', type_='check')
    op.drop_constraint('ck_services_environment', 'services', type_='check')
    op.drop_constraint('ck_users_role', 'users', type_='check')