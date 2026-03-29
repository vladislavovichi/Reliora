"""Application use cases live here."""

from application.use_cases.tickets import (
    AddMessageToTicketUseCase,
    AssignNextQueuedTicketUseCase,
    AssignTicketToOperatorUseCase,
    BasicStatsUseCase,
    CloseTicketUseCase,
    CreateTicketFromClientMessageUseCase,
    EscalateTicketUseCase,
    GetNextQueuedTicketUseCase,
    ListQueuedTicketsUseCase,
)

__all__ = [
    "AddMessageToTicketUseCase",
    "AssignNextQueuedTicketUseCase",
    "AssignTicketToOperatorUseCase",
    "BasicStatsUseCase",
    "CloseTicketUseCase",
    "CreateTicketFromClientMessageUseCase",
    "EscalateTicketUseCase",
    "GetNextQueuedTicketUseCase",
    "ListQueuedTicketsUseCase",
]
