"""Add ticket feedback storage for post-closure surveys.

Revision ID: 20260409_05
Revises: 20260408_04
Create Date: 2026-04-09 12:15:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260409_05"
down_revision = "20260408_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_feedback",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("client_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_ticket_feedback_rating_range"),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_feedback_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_feedback")),
        sa.UniqueConstraint("ticket_id", name=op.f("uq_ticket_feedback_ticket_id")),
    )
    op.create_index(
        op.f("ix_ticket_feedback_ticket_id"),
        "ticket_feedback",
        ["ticket_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ticket_feedback_client_chat_id"),
        "ticket_feedback",
        ["client_chat_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ticket_feedback_client_chat_id"), table_name="ticket_feedback")
    op.drop_index(op.f("ix_ticket_feedback_ticket_id"), table_name="ticket_feedback")
    op.drop_table("ticket_feedback")
