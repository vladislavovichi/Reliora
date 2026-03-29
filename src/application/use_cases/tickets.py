from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from domain.contracts.repositories import (
    OperatorRepository,
    TicketMessageRepository,
    TicketRepository,
)
from domain.enums.tickets import TicketMessageSenderType, TicketStatus


def utcnow() -> datetime:
    return datetime.now(UTC)


def build_ticket_subject(message_text: str) -> str:
    first_line = message_text.strip().splitlines()[0] if message_text.strip() else "Client request"
    return first_line[:255]


def format_public_ticket_number(public_id: UUID) -> str:
    return f"HD-{public_id.hex[:8].upper()}"


@dataclass(slots=True)
class TicketSummary:
    public_id: UUID
    public_number: str
    status: TicketStatus


@dataclass(slots=True)
class TicketStats:
    total: int
    open_total: int
    by_status: dict[TicketStatus, int]


class CreateTicketFromClientMessageUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_message_repository: TicketMessageRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_message_repository = ticket_message_repository

    async def __call__(
        self,
        *,
        client_chat_id: int,
        telegram_message_id: int,
        text: str,
    ) -> TicketSummary:
        ticket = await self.ticket_repository.create(
            client_chat_id=client_chat_id,
            subject=build_ticket_subject(text),
        )
        if ticket.id is None:
            raise RuntimeError("Ticket identifier was not generated.")

        await self.ticket_message_repository.add(
            ticket_id=ticket.id,
            telegram_message_id=telegram_message_id,
            sender_type=TicketMessageSenderType.CLIENT,
            text=text,
        )
        return TicketSummary(
            public_id=ticket.public_id,
            public_number=format_public_ticket_number(ticket.public_id),
            status=ticket.status,
        )


class AddMessageToTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_message_repository: TicketMessageRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_message_repository = ticket_message_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str,
        sender_operator_id: int | None = None,
    ) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        await self.ticket_message_repository.add(
            ticket_id=ticket.id,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            text=text,
            sender_operator_id=sender_operator_id,
        )

        if sender_type == TicketMessageSenderType.OPERATOR and ticket.first_response_at is None:
            ticket.first_response_at = utcnow()

        return TicketSummary(
            public_id=ticket.public_id,
            public_number=format_public_ticket_number(ticket.public_id),
            status=ticket.status,
        )


class AssignTicketToOperatorUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        operator_repository: OperatorRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.operator_repository = operator_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> TicketSummary | None:
        operator_id = await self.operator_repository.get_or_create(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )
        ticket = await self.ticket_repository.assign_to_operator(
            ticket_public_id=ticket_public_id,
            operator_id=operator_id,
        )
        if ticket is None:
            return None

        return TicketSummary(
            public_id=ticket.public_id,
            public_number=format_public_ticket_number(ticket.public_id),
            status=ticket.status,
        )


class CloseTicketUseCase:
    def __init__(self, ticket_repository: TicketRepository) -> None:
        self.ticket_repository = ticket_repository

    async def __call__(self, *, ticket_public_id: UUID) -> TicketSummary | None:
        ticket = await self.ticket_repository.close(ticket_public_id=ticket_public_id)
        if ticket is None:
            return None

        return TicketSummary(
            public_id=ticket.public_id,
            public_number=format_public_ticket_number(ticket.public_id),
            status=ticket.status,
        )


class BasicStatsUseCase:
    def __init__(self, ticket_repository: TicketRepository) -> None:
        self.ticket_repository = ticket_repository

    async def __call__(self) -> TicketStats:
        by_status = dict(await self.ticket_repository.count_by_status())
        total = sum(by_status.values())
        open_total = sum(
            count for status, count in by_status.items() if status != TicketStatus.CLOSED
        )
        return TicketStats(total=total, open_total=open_total, by_status=by_status)
