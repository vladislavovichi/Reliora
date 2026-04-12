from __future__ import annotations

from typing import cast

from sqlalchemy import Table

import infrastructure.db.models  # noqa: F401
from infrastructure.db.base import Base
from infrastructure.db.models.operator import Operator
from infrastructure.db.models.operator_invite import OperatorInviteCode


def test_models_package_populates_base_metadata() -> None:
    assert sorted(Base.metadata.tables.keys()) == [
        "audit_logs",
        "macros",
        "operator_invite_codes",
        "operators",
        "sla_policies",
        "tags",
        "ticket_ai_summaries",
        "ticket_categories",
        "ticket_events",
        "ticket_feedback",
        "ticket_internal_notes",
        "ticket_messages",
        "ticket_tags",
        "tickets",
    ]


def test_operator_telegram_user_id_uses_unique_constraint_and_plain_index() -> None:
    operator_table = cast(Table, Operator.__table__)
    constraint_names = {
        constraint.name for constraint in operator_table.constraints if constraint.name is not None
    }

    assert "uq_operators_telegram_user_id" in constraint_names
    assert any(index.name == "ix_operators_telegram_user_id" for index in operator_table.indexes)
    assert any(
        index.name == "ix_operators_telegram_user_id" and index.unique is False
        for index in operator_table.indexes
    )


def test_operator_invite_code_hash_uses_single_unique_index() -> None:
    invite_table = cast(Table, OperatorInviteCode.__table__)
    constraint_names = {
        constraint.name for constraint in invite_table.constraints if constraint.name is not None
    }

    assert "uq_operator_invite_codes_code_hash" not in constraint_names
    assert any(index.name == "ix_operator_invite_codes_code_hash" for index in invite_table.indexes)
    assert any(
        index.name == "ix_operator_invite_codes_code_hash" and index.unique is True
        for index in invite_table.indexes
    )
