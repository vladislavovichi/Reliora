"""Add operator invite codes for premium onboarding.

Revision ID: 20260412_08
Revises: 20260411_07
Create Date: 2026-04-12 11:20:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260412_08"
down_revision = "20260411_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operator_invite_codes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("created_by_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_uses", sa.Integer(), server_default="1", nullable=False),
        sa.Column("used_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operator_invite_codes")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_operator_invite_codes_code_hash")),
    )
    op.create_index(
        op.f("ix_operator_invite_codes_code_hash"),
        "operator_invite_codes",
        ["code_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_operator_invite_codes_created_by_telegram_user_id"),
        "operator_invite_codes",
        ["created_by_telegram_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operator_invite_codes_expires_at"),
        "operator_invite_codes",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operator_invite_codes_is_active"),
        "operator_invite_codes",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operator_invite_codes_last_used_telegram_user_id"),
        "operator_invite_codes",
        ["last_used_telegram_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_operator_invite_codes_last_used_telegram_user_id"),
        table_name="operator_invite_codes",
    )
    op.drop_index(op.f("ix_operator_invite_codes_is_active"), table_name="operator_invite_codes")
    op.drop_index(op.f("ix_operator_invite_codes_expires_at"), table_name="operator_invite_codes")
    op.drop_index(
        op.f("ix_operator_invite_codes_created_by_telegram_user_id"),
        table_name="operator_invite_codes",
    )
    op.drop_index(op.f("ix_operator_invite_codes_code_hash"), table_name="operator_invite_codes")
    op.drop_table("operator_invite_codes")
