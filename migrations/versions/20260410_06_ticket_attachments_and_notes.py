"""Add ticket attachments and internal operator notes.

Revision ID: 20260410_06
Revises: 20260409_05
Create Date: 2026-04-10 16:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260410_06"
down_revision = "20260409_05"
branch_labels = None
depends_on = None


ticket_attachment_kind = postgresql.ENUM(
    "photo",
    "document",
    "voice",
    "video",
    name="ticket_attachment_kind",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    ticket_attachment_kind.create(bind, checkfirst=True)

    op.add_column(
        "ticket_messages",
        sa.Column("attachment_kind", ticket_attachment_kind, nullable=True),
    )
    op.add_column(
        "ticket_messages",
        sa.Column("attachment_file_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "ticket_messages",
        sa.Column("attachment_file_unique_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "ticket_messages",
        sa.Column("attachment_filename", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "ticket_messages",
        sa.Column("attachment_mime_type", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "ticket_messages",
        sa.Column("attachment_storage_path", sa.String(length=512), nullable=True),
    )
    op.alter_column("ticket_messages", "text", existing_type=sa.Text(), nullable=True)
    op.create_index(
        op.f("ix_ticket_messages_attachment_kind"),
        "ticket_messages",
        ["attachment_kind"],
        unique=False,
    )
    op.drop_constraint(
        op.f("ck_ticket_messages_ticket_message_text_not_empty"),
        "ticket_messages",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ticket_messages_ticket_message_content_not_empty"),
        "ticket_messages",
        "(text IS NOT NULL AND length(btrim(text)) > 0) OR attachment_kind IS NOT NULL",
    )

    op.create_table(
        "ticket_internal_notes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("author_operator_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["author_operator_id"],
            ["operators.id"],
            name=op.f("fk_ticket_internal_notes_author_operator_id_operators"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_internal_notes_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_internal_notes")),
    )
    op.create_index(
        op.f("ix_ticket_internal_notes_author_operator_id"),
        "ticket_internal_notes",
        ["author_operator_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ticket_internal_notes_ticket_id"),
        "ticket_internal_notes",
        ["ticket_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index(
        op.f("ix_ticket_internal_notes_ticket_id"),
        table_name="ticket_internal_notes",
    )
    op.drop_index(
        op.f("ix_ticket_internal_notes_author_operator_id"),
        table_name="ticket_internal_notes",
    )
    op.drop_table("ticket_internal_notes")

    op.drop_constraint(
        op.f("ck_ticket_messages_ticket_message_content_not_empty"),
        "ticket_messages",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ticket_messages_ticket_message_text_not_empty"),
        "ticket_messages",
        "length(text) > 0",
    )
    op.drop_index(op.f("ix_ticket_messages_attachment_kind"), table_name="ticket_messages")
    op.alter_column("ticket_messages", "text", existing_type=sa.Text(), nullable=False)
    op.drop_column("ticket_messages", "attachment_mime_type")
    op.drop_column("ticket_messages", "attachment_storage_path")
    op.drop_column("ticket_messages", "attachment_filename")
    op.drop_column("ticket_messages", "attachment_file_unique_id")
    op.drop_column("ticket_messages", "attachment_file_id")
    op.drop_column("ticket_messages", "attachment_kind")

    ticket_attachment_kind.drop(bind, checkfirst=True)
