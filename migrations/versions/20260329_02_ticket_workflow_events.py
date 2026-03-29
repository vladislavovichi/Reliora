"""Extend ticket event enum for workflow tracking.

Revision ID: 20260329_02
Revises: 20260329_01
Create Date: 2026-03-29 21:15:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260329_02"
down_revision = "20260329_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE ticket_event_type ADD VALUE IF NOT EXISTS 'queued'")
    op.execute("ALTER TYPE ticket_event_type ADD VALUE IF NOT EXISTS 'reassigned'")
    op.execute("ALTER TYPE ticket_event_type ADD VALUE IF NOT EXISTS 'client_message_added'")
    op.execute("ALTER TYPE ticket_event_type ADD VALUE IF NOT EXISTS 'operator_message_added'")


def downgrade() -> None:
    op.execute(
        """
        UPDATE ticket_events
        SET event_type = 'status_changed'
        WHERE event_type = 'queued'
        """
    )
    op.execute(
        """
        UPDATE ticket_events
        SET event_type = 'assigned'
        WHERE event_type = 'reassigned'
        """
    )
    op.execute(
        """
        UPDATE ticket_events
        SET event_type = 'message_added'
        WHERE event_type IN ('client_message_added', 'operator_message_added')
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
            'closed'
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
