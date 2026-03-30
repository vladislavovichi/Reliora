from __future__ import annotations

from domain.enums.tickets import TicketStatus

OPEN_TICKET_STATUSES = frozenset(
    {
        TicketStatus.NEW,
        TicketStatus.QUEUED,
        TicketStatus.ASSIGNED,
        TicketStatus.ESCALATED,
    }
)
ASSIGNABLE_TICKET_STATUSES = frozenset(
    {
        TicketStatus.NEW,
        TicketStatus.QUEUED,
        TicketStatus.ASSIGNED,
        TicketStatus.ESCALATED,
    }
)
ESCALATABLE_TICKET_STATUSES = frozenset(
    {
        TicketStatus.QUEUED,
        TicketStatus.ASSIGNED,
    }
)
OPERATOR_REPLYABLE_TICKET_STATUSES = frozenset(
    {
        TicketStatus.ASSIGNED,
        TicketStatus.ESCALATED,
    }
)


class InvalidTicketTransitionError(ValueError):
    """Raised when a workflow action is not valid for the current ticket state."""


def format_status_for_humans(status: TicketStatus) -> str:
    status_labels = {
        TicketStatus.NEW: "новый",
        TicketStatus.QUEUED: "в очереди",
        TicketStatus.ASSIGNED: "назначен",
        TicketStatus.ESCALATED: "эскалирован",
        TicketStatus.CLOSED: "закрыт",
    }
    return status_labels.get(status, status.value)


def is_open_status(status: TicketStatus) -> bool:
    return status in OPEN_TICKET_STATUSES


def ensure_assignable(status: TicketStatus) -> None:
    if status not in ASSIGNABLE_TICKET_STATUSES:
        raise InvalidTicketTransitionError(
            "Заявку нельзя назначить, пока она находится "
            f"в статусе «{format_status_for_humans(status)}»."
        )


def ensure_escalatable(status: TicketStatus) -> None:
    if status not in ESCALATABLE_TICKET_STATUSES:
        raise InvalidTicketTransitionError(
            "Заявку нельзя эскалировать, пока она находится "
            f"в статусе «{format_status_for_humans(status)}»."
        )


def ensure_closable(status: TicketStatus) -> None:
    if not is_open_status(status):
        raise InvalidTicketTransitionError(
            "Заявку нельзя закрыть, пока она находится "
            f"в статусе «{format_status_for_humans(status)}»."
        )


def ensure_message_addable(status: TicketStatus) -> None:
    if not is_open_status(status):
        raise InvalidTicketTransitionError(
            "Нельзя добавлять сообщения, пока заявка находится "
            f"в статусе «{format_status_for_humans(status)}»."
        )


def ensure_operator_replyable(status: TicketStatus) -> None:
    if status not in OPERATOR_REPLYABLE_TICKET_STATUSES:
        raise InvalidTicketTransitionError(
            "Ответ оператора недоступен, пока заявка находится "
            f"в статусе «{format_status_for_humans(status)}»."
        )
