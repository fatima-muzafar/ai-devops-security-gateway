"""approval_requests: decided_at, unique request_id, state_snapshot, revalidation (decisions.md #81)

Revision ID: e7c1a4b9d2f6
Revises: d5b2f8a1c7e3
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7c1a4b9d2f6'
down_revision: Union[str, Sequence[str], None] = 'd5b2f8a1c7e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Hand-written. No new table (still 11).

    approved_at -> decided_at (set on approve AND reject); UNIQUE(request_id);
    state_snapshot JSON NOT NULL (server default '{}' so existing rows, if any, stay valid);
    revalidation Text NULL (NULL = not run).
    """
    op.alter_column('approval_requests', 'approved_at', new_column_name='decided_at')
    op.create_unique_constraint(
        'uq_approval_requests_request_id', 'approval_requests', ['request_id']
    )
    op.add_column(
        'approval_requests',
        sa.Column('state_snapshot', sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column('approval_requests', sa.Column('revalidation', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema. The snapshot and revalidation evidence is lost (dev databases only)."""
    op.drop_column('approval_requests', 'revalidation')
    op.drop_column('approval_requests', 'state_snapshot')
    op.drop_constraint('uq_approval_requests_request_id', 'approval_requests', type_='unique')
    op.alter_column('approval_requests', 'decided_at', new_column_name='approved_at')
