from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from uuid import UUID

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
    QueuedTicketSummary,
    TicketStats,
    TicketSummary,
)
from domain.contracts.repositories import (
    OperatorRepository,
    TicketEventRepository,
    TicketMessageRepository,
    TicketRepository,
)
from domain.enums.tickets import TicketMessageSenderType

HelpdeskServiceFactory = Callable[[], AbstractAsyncContextManager["HelpdeskService"]]


@dataclass(slots=True)
class HelpdeskService:
    ticket_repository: TicketRepository
    ticket_message_repository: TicketMessageRepository
    ticket_event_repository: TicketEventRepository
    operator_repository: OperatorRepository
    _create_ticket_from_client_message: CreateTicketFromClientMessageUseCase = field(
        init=False,
        repr=False,
    )
    _add_message_to_ticket: AddMessageToTicketUseCase = field(init=False, repr=False)
    _assign_ticket_to_operator: AssignTicketToOperatorUseCase = field(init=False, repr=False)
    _get_next_queued_ticket: GetNextQueuedTicketUseCase = field(init=False, repr=False)
    _list_queued_tickets: ListQueuedTicketsUseCase = field(init=False, repr=False)
    _assign_next_queued_ticket: AssignNextQueuedTicketUseCase = field(init=False, repr=False)
    _escalate_ticket: EscalateTicketUseCase = field(init=False, repr=False)
    _close_ticket: CloseTicketUseCase = field(init=False, repr=False)
    _get_basic_stats: BasicStatsUseCase = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._create_ticket_from_client_message = CreateTicketFromClientMessageUseCase(
            ticket_repository=self.ticket_repository,
            ticket_message_repository=self.ticket_message_repository,
            ticket_event_repository=self.ticket_event_repository,
        )
        self._add_message_to_ticket = AddMessageToTicketUseCase(
            ticket_repository=self.ticket_repository,
            ticket_message_repository=self.ticket_message_repository,
            ticket_event_repository=self.ticket_event_repository,
        )
        self._assign_ticket_to_operator = AssignTicketToOperatorUseCase(
            ticket_repository=self.ticket_repository,
            ticket_event_repository=self.ticket_event_repository,
            operator_repository=self.operator_repository,
        )
        self._get_next_queued_ticket = GetNextQueuedTicketUseCase(
            ticket_repository=self.ticket_repository,
        )
        self._list_queued_tickets = ListQueuedTicketsUseCase(
            ticket_repository=self.ticket_repository,
        )
        self._assign_next_queued_ticket = AssignNextQueuedTicketUseCase(
            ticket_repository=self.ticket_repository,
            ticket_event_repository=self.ticket_event_repository,
            operator_repository=self.operator_repository,
        )
        self._escalate_ticket = EscalateTicketUseCase(
            ticket_repository=self.ticket_repository,
            ticket_event_repository=self.ticket_event_repository,
        )
        self._close_ticket = CloseTicketUseCase(
            ticket_repository=self.ticket_repository,
            ticket_event_repository=self.ticket_event_repository,
        )
        self._get_basic_stats = BasicStatsUseCase(ticket_repository=self.ticket_repository)

    async def create_ticket_from_client_message(
        self,
        *,
        client_chat_id: int,
        telegram_message_id: int,
        text: str,
    ) -> TicketSummary:
        return await self._create_ticket_from_client_message(
            client_chat_id=client_chat_id,
            telegram_message_id=telegram_message_id,
            text=text,
        )

    async def add_message_to_ticket(
        self,
        *,
        ticket_public_id: UUID,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str,
        sender_operator_id: int | None = None,
    ) -> TicketSummary | None:
        return await self._add_message_to_ticket(
            ticket_public_id=ticket_public_id,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            text=text,
            sender_operator_id=sender_operator_id,
        )

    async def assign_ticket_to_operator(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> TicketSummary | None:
        return await self._assign_ticket_to_operator(
            ticket_public_id=ticket_public_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )

    async def close_ticket(self, *, ticket_public_id: UUID) -> TicketSummary | None:
        return await self._close_ticket(ticket_public_id=ticket_public_id)

    async def get_next_queued_ticket(
        self,
        *,
        prioritize_priority: bool = False,
    ) -> QueuedTicketSummary | None:
        return await self._get_next_queued_ticket(prioritize_priority=prioritize_priority)

    async def list_queued_tickets(
        self,
        *,
        limit: int | None = None,
        prioritize_priority: bool = False,
    ) -> Sequence[QueuedTicketSummary]:
        return await self._list_queued_tickets(
            limit=limit,
            prioritize_priority=prioritize_priority,
        )

    async def assign_next_ticket_to_operator(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
        prioritize_priority: bool = False,
    ) -> TicketSummary | None:
        return await self._assign_next_queued_ticket(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
            prioritize_priority=prioritize_priority,
        )

    async def escalate_ticket(self, *, ticket_public_id: UUID) -> TicketSummary | None:
        return await self._escalate_ticket(ticket_public_id=ticket_public_id)

    async def get_basic_stats(self) -> TicketStats:
        return await self._get_basic_stats()
