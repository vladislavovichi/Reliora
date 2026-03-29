from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from uuid import UUID

from application.use_cases.tickets import (
    AddMessageToTicketUseCase,
    AssignTicketToOperatorUseCase,
    BasicStatsUseCase,
    CloseTicketUseCase,
    CreateTicketFromClientMessageUseCase,
    TicketStats,
    TicketSummary,
    format_public_ticket_number,
)
from domain.contracts.repositories import (
    OperatorRepository,
    TicketMessageRepository,
    TicketRepository,
)
from domain.enums.tickets import TicketMessageSenderType

HelpdeskServiceFactory = Callable[[], AbstractAsyncContextManager["HelpdeskService"]]


@dataclass(slots=True)
class HelpdeskService:
    ticket_repository: TicketRepository
    ticket_message_repository: TicketMessageRepository
    operator_repository: OperatorRepository
    _create_ticket_from_client_message: CreateTicketFromClientMessageUseCase = field(
        init=False,
        repr=False,
    )
    _add_message_to_ticket: AddMessageToTicketUseCase = field(init=False, repr=False)
    _assign_ticket_to_operator: AssignTicketToOperatorUseCase = field(init=False, repr=False)
    _close_ticket: CloseTicketUseCase = field(init=False, repr=False)
    _get_basic_stats: BasicStatsUseCase = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._create_ticket_from_client_message = CreateTicketFromClientMessageUseCase(
            ticket_repository=self.ticket_repository,
            ticket_message_repository=self.ticket_message_repository,
        )
        self._add_message_to_ticket = AddMessageToTicketUseCase(
            ticket_repository=self.ticket_repository,
            ticket_message_repository=self.ticket_message_repository,
        )
        self._assign_ticket_to_operator = AssignTicketToOperatorUseCase(
            ticket_repository=self.ticket_repository,
            operator_repository=self.operator_repository,
        )
        self._close_ticket = CloseTicketUseCase(ticket_repository=self.ticket_repository)
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

    async def get_basic_stats(self) -> TicketStats:
        return await self._get_basic_stats()

    async def acknowledge_reply_action(self, *, ticket_public_id: UUID) -> str:
        return await self._acknowledge_placeholder_action(
            ticket_public_id=ticket_public_id,
            action_name="Reply",
        )

    async def acknowledge_escalate_action(self, *, ticket_public_id: UUID) -> str:
        return await self._acknowledge_placeholder_action(
            ticket_public_id=ticket_public_id,
            action_name="Escalation",
        )

    async def _acknowledge_placeholder_action(
        self,
        *,
        ticket_public_id: UUID,
        action_name: str,
    ) -> str:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None:
            return "Ticket not found."

        return (
            f"{action_name} flow for ticket {format_public_ticket_number(ticket.public_id)} "
            "is not implemented yet."
        )
