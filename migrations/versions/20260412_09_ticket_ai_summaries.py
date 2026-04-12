"""Add persisted AI summaries for operator assist.

Revision ID: 20260412_09
Revises: 20260412_08
Create Date: 2026-04-12 18:35:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260412_09"
down_revision = "20260412_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_ai_summaries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("short_summary", sa.Text(), nullable=False),
        sa.Column("user_goal", sa.Text(), nullable=False),
        sa.Column("actions_taken", sa.Text(), nullable=False),
        sa.Column("current_status", sa.Text(), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_ticket_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_message_count", sa.Integer(), nullable=False),
        sa.Column("source_internal_note_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_ai_summaries_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_ai_summaries")),
        sa.UniqueConstraint("ticket_id", name=op.f("uq_ticket_ai_summaries_ticket_id")),
    )
    op.create_index(
        op.f("ix_ticket_ai_summaries_generated_at"),
        "ticket_ai_summaries",
        ["generated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ticket_ai_summaries_ticket_id"),
        "ticket_ai_summaries",
        ["ticket_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ticket_ai_summaries_ticket_id"), table_name="ticket_ai_summaries")
    op.drop_index(op.f("ix_ticket_ai_summaries_generated_at"), table_name="ticket_ai_summaries")
    op.drop_table("ticket_ai_summaries")
