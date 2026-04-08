"""Add ticket categories and attach them to tickets.

Revision ID: 20260408_04
Revises: 20260330_03
Create Date: 2026-04-08 12:40:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260408_04"
down_revision = "20260330_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_categories",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_categories")),
        sa.UniqueConstraint("code", name=op.f("uq_ticket_categories_code")),
        sa.UniqueConstraint("title", name=op.f("uq_ticket_categories_title")),
    )
    op.add_column("tickets", sa.Column("category_id", sa.BigInteger(), nullable=True))
    op.create_index(op.f("ix_tickets_category_id"), "tickets", ["category_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_tickets_category_id_ticket_categories"),
        "tickets",
        "ticket_categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )

    categories_table = sa.table(
        "ticket_categories",
        sa.column("code", sa.String(length=50)),
        sa.column("title", sa.String(length=120)),
        sa.column("is_active", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
    )
    op.bulk_insert(
        categories_table,
        [
            {
                "code": "access",
                "title": "Доступ и вход",
                "is_active": True,
                "sort_order": 10,
            },
            {
                "code": "billing",
                "title": "Оплата и документы",
                "is_active": True,
                "sort_order": 20,
            },
            {
                "code": "setup",
                "title": "Настройка сервиса",
                "is_active": True,
                "sort_order": 30,
            },
            {
                "code": "bug",
                "title": "Техническая ошибка",
                "is_active": True,
                "sort_order": 40,
            },
            {
                "code": "other",
                "title": "Другая тема",
                "is_active": True,
                "sort_order": 90,
            },
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_tickets_category_id_ticket_categories"),
        "tickets",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_tickets_category_id"), table_name="tickets")
    op.drop_column("tickets", "category_id")
    op.drop_table("ticket_categories")
