"""Initial helpdesk schema.

Revision ID: 20260329_01
Revises:
Create Date: 2026-03-29 18:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260329_01"
down_revision = None
branch_labels = None
depends_on = None


ticket_status = sa.Enum(
    "new",
    "queued",
    "assigned",
    "escalated",
    "closed",
    name="ticket_status",
)
ticket_priority = sa.Enum(
    "low",
    "normal",
    "high",
    "urgent",
    name="ticket_priority",
)
ticket_message_sender_type = sa.Enum(
    "client",
    "operator",
    "system",
    name="ticket_message_sender_type",
)
ticket_event_type = sa.Enum(
    "created",
    "status_changed",
    "assigned",
    "message_added",
    "tag_added",
    "tag_removed",
    "escalated",
    "closed",
    name="ticket_event_type",
)


def upgrade() -> None:
    bind = op.get_bind()

    ticket_status.create(bind, checkfirst=True)
    ticket_priority.create(bind, checkfirst=True)
    ticket_message_sender_type.create(bind, checkfirst=True)
    ticket_event_type.create(bind, checkfirst=True)

    op.create_table(
        "operators",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operators")),
        sa.UniqueConstraint("telegram_user_id", name=op.f("uq_operators_telegram_user_id")),
    )
    op.create_index(op.f("ix_operators_telegram_user_id"), "operators", ["telegram_user_id"], unique=False)
    op.create_index(op.f("ix_operators_username"), "operators", ["username"], unique=False)

    op.create_table(
        "macros",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_macros")),
        sa.UniqueConstraint("title", name=op.f("uq_macros_title")),
    )

    op.create_table(
        "sla_policies",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("first_response_minutes", sa.Integer(), nullable=False),
        sa.Column("resolution_minutes", sa.Integer(), nullable=False),
        sa.Column("priority", ticket_priority, nullable=True),
        sa.CheckConstraint(
            "first_response_minutes > 0",
            name=op.f("ck_sla_policies_first_response_minutes_positive"),
        ),
        sa.CheckConstraint(
            "resolution_minutes > 0",
            name=op.f("ck_sla_policies_resolution_minutes_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sla_policies")),
        sa.UniqueConstraint("name", name=op.f("uq_sla_policies_name")),
    )
    op.create_index(op.f("ix_sla_policies_priority"), "sla_policies", ["priority"], unique=False)

    op.create_table(
        "tags",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("name", name=op.f("uq_tags_name")),
    )

    op.create_table(
        "tickets",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("status", ticket_status, server_default=sa.text("'new'"), nullable=False),
        sa.Column("priority", ticket_priority, server_default=sa.text("'normal'"), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("assigned_operator_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assigned_operator_id"],
            ["operators.id"],
            name=op.f("fk_tickets_assigned_operator_id_operators"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
        sa.UniqueConstraint("public_id", name=op.f("uq_tickets_public_id")),
    )
    op.create_index(op.f("ix_tickets_assigned_operator_id"), "tickets", ["assigned_operator_id"], unique=False)
    op.create_index(op.f("ix_tickets_client_chat_id"), "tickets", ["client_chat_id"], unique=False)
    op.create_index(op.f("ix_tickets_priority"), "tickets", ["priority"], unique=False)
    op.create_index(op.f("ix_tickets_status"), "tickets", ["status"], unique=False)

    op.create_table(
        "ticket_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", ticket_event_type, nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_events_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_events")),
    )
    op.create_index(op.f("ix_ticket_events_event_type"), "ticket_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_ticket_events_ticket_id"), "ticket_events", ["ticket_id"], unique=False)

    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_type", ticket_message_sender_type, nullable=False),
        sa.Column("sender_operator_id", sa.BigInteger(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(text) > 0", name=op.f("ck_ticket_messages_ticket_message_text_not_empty")),
        sa.ForeignKeyConstraint(
            ["sender_operator_id"],
            ["operators.id"],
            name=op.f("fk_ticket_messages_sender_operator_id_operators"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_messages_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_messages")),
        sa.UniqueConstraint(
            "ticket_id",
            "telegram_message_id",
            "sender_type",
            name=op.f("uq_ticket_messages_ticket_telegram_sender"),
        ),
    )
    op.create_index(op.f("ix_ticket_messages_sender_operator_id"), "ticket_messages", ["sender_operator_id"], unique=False)
    op.create_index(op.f("ix_ticket_messages_ticket_id"), "ticket_messages", ["ticket_id"], unique=False)

    op.create_table(
        "ticket_tags",
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["tags.id"],
            name=op.f("fk_ticket_tags_tag_id_tags"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_tags_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ticket_id", "tag_id", name=op.f("pk_ticket_tags")),
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_table("ticket_tags")

    op.drop_index(op.f("ix_ticket_messages_ticket_id"), table_name="ticket_messages")
    op.drop_index(op.f("ix_ticket_messages_sender_operator_id"), table_name="ticket_messages")
    op.drop_table("ticket_messages")

    op.drop_index(op.f("ix_ticket_events_ticket_id"), table_name="ticket_events")
    op.drop_index(op.f("ix_ticket_events_event_type"), table_name="ticket_events")
    op.drop_table("ticket_events")

    op.drop_index(op.f("ix_tickets_status"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_priority"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_client_chat_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_assigned_operator_id"), table_name="tickets")
    op.drop_table("tickets")

    op.drop_table("tags")

    op.drop_index(op.f("ix_sla_policies_priority"), table_name="sla_policies")
    op.drop_table("sla_policies")

    op.drop_table("macros")

    op.drop_index(op.f("ix_operators_username"), table_name="operators")
    op.drop_index(op.f("ix_operators_telegram_user_id"), table_name="operators")
    op.drop_table("operators")

    ticket_event_type.drop(bind, checkfirst=True)
    ticket_message_sender_type.drop(bind, checkfirst=True)
    ticket_priority.drop(bind, checkfirst=True)
    ticket_status.drop(bind, checkfirst=True)
