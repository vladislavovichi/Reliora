from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import case
from sqlalchemy.sql import Select

from domain.enums.tickets import TicketPriority
from infrastructure.db.models import Ticket as TicketModel


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_tag_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def apply_queue_ordering(
    statement: Select[tuple[TicketModel]],
    *,
    prioritize_priority: bool,
) -> Select[tuple[TicketModel]]:
    if not prioritize_priority:
        return statement.order_by(TicketModel.created_at.asc(), TicketModel.id.asc())

    priority_rank = case(
        (TicketModel.priority == TicketPriority.URGENT, 0),
        (TicketModel.priority == TicketPriority.HIGH, 1),
        (TicketModel.priority == TicketPriority.NORMAL, 2),
        (TicketModel.priority == TicketPriority.LOW, 3),
        else_=4,
    )
    return statement.order_by(
        priority_rank.asc(),
        TicketModel.created_at.asc(),
        TicketModel.id.asc(),
    )


@dataclass(slots=True, frozen=True)
class OperatorTicketLoadRow:
    operator_id: int
    display_name: str
    ticket_count: int
