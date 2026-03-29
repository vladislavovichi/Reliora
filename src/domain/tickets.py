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


class InvalidTicketTransitionError(ValueError):
    """Raised when a workflow action is not valid for the current ticket state."""


def is_open_status(status: TicketStatus) -> bool:
    return status in OPEN_TICKET_STATUSES


def ensure_assignable(status: TicketStatus) -> None:
    if status not in ASSIGNABLE_TICKET_STATUSES:
        raise InvalidTicketTransitionError(
            f"Ticket cannot be assigned while in status {status.value!r}."
        )


def ensure_escalatable(status: TicketStatus) -> None:
    if status not in ESCALATABLE_TICKET_STATUSES:
        raise InvalidTicketTransitionError(
            f"Ticket cannot be escalated while in status {status.value!r}."
        )


def ensure_closable(status: TicketStatus) -> None:
    if not is_open_status(status):
        raise InvalidTicketTransitionError(
            f"Ticket cannot be closed while in status {status.value!r}."
        )


def ensure_message_addable(status: TicketStatus) -> None:
    if not is_open_status(status):
        raise InvalidTicketTransitionError(
            f"Messages cannot be added while the ticket is {status.value!r}."
        )
