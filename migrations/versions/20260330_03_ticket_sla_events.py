"""Add SLA-specific ticket event types.

Revision ID: 20260330_03
Revises: 20260329_02
Create Date: 2026-03-30 12:10:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260330_03"
down_revision = "20260329_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE ticket_event_type ADD VALUE IF NOT EXISTS 'sla_breached_first_response'"
    )
    op.execute(
        "ALTER TYPE ticket_event_type ADD VALUE IF NOT EXISTS 'sla_breached_resolution'"
    )
    op.execute("ALTER TYPE ticket_event_type ADD VALUE IF NOT EXISTS 'auto_escalated'")
    op.execute("ALTER TYPE ticket_event_type ADD VALUE IF NOT EXISTS 'auto_reassigned'")


def downgrade() -> None:
    op.execute(
        """
        UPDATE ticket_events
        SET event_type = 'escalated'
        WHERE event_type IN ('sla_breached_first_response', 'sla_breached_resolution')
        """
    )
    op.execute(
        """
        UPDATE ticket_events
        SET event_type = 'escalated'
        WHERE event_type = 'auto_escalated'
        """
    )
    op.execute(
        """
        UPDATE ticket_events
        SET event_type = 'reassigned'
        WHERE event_type = 'auto_reassigned'
        """
    )
    op.execute("ALTER TYPE ticket_event_type RENAME TO ticket_event_type_old")
    op.execute(
        """
        CREATE TYPE ticket_event_type AS ENUM (
            'created',
            'status_changed',
            'assigned',
            'message_added',
            'tag_added',
            'tag_removed',
            'escalated',
            'closed',
            'queued',
            'reassigned',
            'client_message_added',
            'operator_message_added'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE ticket_events
        ALTER COLUMN event_type
        TYPE ticket_event_type
        USING event_type::text::ticket_event_type
        """
    )
    op.execute("DROP TYPE ticket_event_type_old")
