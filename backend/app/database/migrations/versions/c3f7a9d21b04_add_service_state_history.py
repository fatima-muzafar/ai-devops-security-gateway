"""add service_state_history table (decisions.md #7)

Revision ID: c3f7a9d21b04
Revises: 6b86e1e35917
Create Date: 2026-09-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f7a9d21b04'
down_revision: Union[str, Sequence[str], None] = '6b86e1e35917'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    decisions.md #7: one unified history table for restart/rollback/deploy
    state transitions, not two near-identical tables. This is table 11;
    decisions.md's earlier "10 tables" line was a Phase 2 snapshot, not a
    ceiling — logged explicitly as its own decision rather than silently
    changed.

    Unlike migration 0b6eff3ade85 (which needed a follow-up migration to
    patch in missing CHECK constraints), the check constraint here is
    created inline at table-creation time.
    """
    op.create_table(
        'service_state_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('change_type', sa.Enum('deploy', 'restart', 'rollback', name='change_type', native_enum=False), nullable=False),
        sa.Column('version_before', sa.Integer(), nullable=True),
        sa.Column('version_after', sa.Integer(), nullable=True),
        sa.Column('status_before', sa.String(length=32), nullable=False),
        sa.Column('status_after', sa.String(length=32), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['service_id'], ['services.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("change_type IN ('deploy', 'restart', 'rollback')", name='ck_service_state_history_change_type'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('service_state_history')