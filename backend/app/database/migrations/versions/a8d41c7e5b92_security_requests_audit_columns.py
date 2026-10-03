"""security_requests audit columns (decisions.md #32, #39)

Revision ID: a8d41c7e5b92
Revises: c3f7a9d21b04
Create Date: 2026-10-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8d41c7e5b92'
down_revision: Union[str, Sequence[str], None] = 'c3f7a9d21b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NULLABLE_COLUMNS = ('user_id', 'agent_id', 'service_id', 'tool_id', 'environment')


def upgrade() -> None:
    """Upgrade schema.

    decisions.md #32 + #39: let the table audit requests whose identity,
    tool, service or environment did not resolve; add raw_request, reason
    and execution_status. No new table (still 11 tables).

    The existing CHECK constraint on `environment` (migration 6b86e1e35917)
    is left in place: a SQL CHECK evaluates NULL as "unknown" and passes,
    so NULL is allowed while invalid non-NULL strings are still rejected.
    """
    for column in _NULLABLE_COLUMNS:
        op.alter_column('security_requests', column, nullable=True)

    op.add_column(
        'security_requests',
        sa.Column('raw_request', sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column(
        'security_requests',
        sa.Column('reason', sa.Text(), nullable=True),
    )
    op.add_column(
        'security_requests',
        sa.Column(
            'execution_status',
            sa.Enum('not_executed', 'executed', 'failed', name='executionstatus', native_enum=False),
            server_default='not_executed',
            nullable=False,
        ),
    )
    op.create_check_constraint(
        'ck_security_requests_execution_status',
        'security_requests',
        "execution_status IN ('not_executed', 'executed', 'failed')",
    )


def downgrade() -> None:
    """Downgrade schema.

    WARNING: the old schema cannot represent unresolved requests, so rows
    with a NULL user/agent/service/tool/environment are DELETED here --
    otherwise restoring NOT NULL would fail. This destroys audit rows;
    only downgrade on a dev database.
    """
    op.execute(
        "DELETE FROM security_requests WHERE "
        + " OR ".join(f"{c} IS NULL" for c in _NULLABLE_COLUMNS)
    )
    op.drop_constraint('ck_security_requests_execution_status', 'security_requests', type_='check')
    op.drop_column('security_requests', 'execution_status')
    op.drop_column('security_requests', 'reason')
    op.drop_column('security_requests', 'raw_request')
    for column in _NULLABLE_COLUMNS:
        op.alter_column('security_requests', column, nullable=False)