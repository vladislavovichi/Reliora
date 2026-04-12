"""Drop redundant unique constraint for operator invite code hashes.

Revision ID: 20260413_10
Revises: 20260412_09
Create Date: 2026-04-13 01:10:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260413_10"
down_revision = "20260412_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("uq_operator_invite_codes_code_hash"),
        "operator_invite_codes",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        op.f("uq_operator_invite_codes_code_hash"),
        "operator_invite_codes",
        ["code_hash"],
    )
