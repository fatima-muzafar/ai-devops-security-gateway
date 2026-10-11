"""behavior_events: source marker, request_id FK, 'failed' outcome (decisions.md #65, #66, #75)

Revision ID: d5b2f8a1c7e3
Revises: a8d41c7e5b92
Create Date: 2026-10-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5b2f8a1c7e3'
down_revision: Union[str, Sequence[str], None] = 'a8d41c7e5b92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Hand-written (autogenerate does not detect CHECK changes).

    (a) `source` NOT NULL default 'live' + CHECK (#65);
    (b) `request_id` String(32), nullable, FK -> security_requests.request_id (#75);
    (c) ck_behavior_events_outcome recreated with 'failed' (#66).
    No new table (still 11). Existing rows, if any, become source='live'.
    """
    op.add_column(
        'behavior_events',
        sa.Column(
            'source',
            sa.Enum('live', 'synthetic', name='eventsource', native_enum=False),
            server_default='live',
            nullable=False,
        ),
    )
    op.create_check_constraint(
        'ck_behavior_events_source', 'behavior_events', "source IN ('live', 'synthetic')"
    )
    op.add_column('behavior_events', sa.Column('request_id', sa.String(length=32), nullable=True))
    op.create_foreign_key(
        'fk_behavior_events_request_id_security_requests',
        'behavior_events',
        'security_requests',
        ['request_id'],
        ['request_id'],
    )
    op.drop_constraint('ck_behavior_events_outcome', 'behavior_events', type_='check')
    op.create_check_constraint(
        'ck_behavior_events_outcome',
        'behavior_events',
        "outcome IN ('allowed', 'blocked', 'pending', 'failed')",
    )


def downgrade() -> None:
    """Downgrade schema.

    WARNING: rows with outcome='failed' are DELETED first (regenerable telemetry), because
    restoring the old CHECK would fail otherwise. The source and request_id columns are
    dropped, so the live/synthetic distinction is lost. Dev databases only.
    """
    op.execute("DELETE FROM behavior_events WHERE outcome = 'failed'")
    op.drop_constraint('ck_behavior_events_outcome', 'behavior_events', type_='check')
    op.create_check_constraint(
        'ck_behavior_events_outcome',
        'behavior_events',
        "outcome IN ('allowed', 'blocked', 'pending')",
    )
    op.drop_constraint('fk_behavior_events_request_id_security_requests', 'behavior_events', type_='foreignkey')
    op.drop_column('behavior_events', 'request_id')
    op.drop_constraint('ck_behavior_events_source', 'behavior_events', type_='check')
    op.drop_column('behavior_events', 'source')
