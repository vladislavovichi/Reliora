from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from domain.contracts.repositories import (
    OperatorRepository,
    TicketEventRepository,
    TicketMessageRepository,
    TicketRepository,
)
from domain.entities.ticket import Ticket
from domain.enums.tickets import TicketEventType, TicketMessageSenderType, TicketStatus
from domain.tickets import (
    InvalidTicketTransitionError,
    ensure_assignable,
    ensure_closable,
    ensure_escalatable,
    ensure_message_addable,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def build_ticket_subject(message_text: str) -> str:
    first_line = message_text.strip().splitlines()[0] if message_text.strip() else "Client request"
    return first_line[:255]


def format_public_ticket_number(public_id: UUID) -> str:
    return f"HD-{public_id.hex[:8].upper()}"


def build_ticket_summary(
    ticket: Ticket,
    *,
    created: bool = False,
    event_type: TicketEventType | None = None,
) -> TicketSummary:
    return TicketSummary(
        public_id=ticket.public_id,
        public_number=format_public_ticket_number(ticket.public_id),
        status=ticket.status,
        created=created,
        event_type=event_type,
    )


def build_status_payload(
    *,
    from_status: TicketStatus,
    to_status: TicketStatus,
    assigned_operator_id: int | None,
    previous_operator_id: int | None = None,
    actor_operator_id: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "from_status": from_status.value,
        "to_status": to_status.value,
    }
    if assigned_operator_id is not None:
        payload["assigned_operator_id"] = assigned_operator_id
    if previous_operator_id is not None:
        payload["previous_operator_id"] = previous_operator_id
    if actor_operator_id is not None:
        payload["actor_operator_id"] = actor_operator_id
    return payload


def build_message_payload(
    *,
    telegram_message_id: int,
    sender_type: TicketMessageSenderType,
    sender_operator_id: int | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "telegram_message_id": telegram_message_id,
        "sender_type": sender_type.value,
    }
    if sender_operator_id is not None:
        payload["sender_operator_id"] = sender_operator_id
    return payload


def build_event_type_for_message(
    sender_type: TicketMessageSenderType,
) -> TicketEventType | None:
    if sender_type == TicketMessageSenderType.CLIENT:
        return TicketEventType.CLIENT_MESSAGE_ADDED
    if sender_type == TicketMessageSenderType.OPERATOR:
        return TicketEventType.OPERATOR_MESSAGE_ADDED
    return None


@dataclass(slots=True)
class TicketSummary:
    public_id: UUID
    public_number: str
    status: TicketStatus
    created: bool = False
    event_type: TicketEventType | None = None


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
        ticket_event_repository: TicketEventRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_message_repository = ticket_message_repository
        self.ticket_event_repository = ticket_event_repository

    async def __call__(
        self,
        *,
        client_chat_id: int,
        telegram_message_id: int,
        text: str,
    ) -> TicketSummary:
        active_ticket = await self.ticket_repository.get_active_by_client_chat_id(client_chat_id)
        if active_ticket is not None:
            if active_ticket.id is None:
                raise RuntimeError("Active ticket identifier is missing.")

            ensure_message_addable(active_ticket.status)
            await self.ticket_message_repository.add(
                ticket_id=active_ticket.id,
                telegram_message_id=telegram_message_id,
                sender_type=TicketMessageSenderType.CLIENT,
                text=text,
            )
            await self.ticket_event_repository.add(
                ticket_id=active_ticket.id,
                event_type=TicketEventType.CLIENT_MESSAGE_ADDED,
                payload_json=build_message_payload(
                    telegram_message_id=telegram_message_id,
                    sender_type=TicketMessageSenderType.CLIENT,
                    sender_operator_id=None,
                ),
            )
            return build_ticket_summary(
                active_ticket,
                created=False,
                event_type=TicketEventType.CLIENT_MESSAGE_ADDED,
            )

        ticket = await self.ticket_repository.create(
            client_chat_id=client_chat_id,
            subject=build_ticket_subject(text),
        )
        if ticket.id is None:
            raise RuntimeError("Ticket identifier was not generated.")

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.CREATED,
            payload_json={
                "status": ticket.status.value,
                "subject": ticket.subject,
                "client_chat_id": ticket.client_chat_id,
            },
        )

        queued_ticket = await self.ticket_repository.enqueue(ticket_public_id=ticket.public_id)
        if queued_ticket is None:
            raise RuntimeError("Ticket could not be placed into the queue.")

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.QUEUED,
            payload_json=build_status_payload(
                from_status=TicketStatus.NEW,
                to_status=queued_ticket.status,
                assigned_operator_id=queued_ticket.assigned_operator_id,
            ),
        )

        await self.ticket_message_repository.add(
            ticket_id=ticket.id,
            telegram_message_id=telegram_message_id,
            sender_type=TicketMessageSenderType.CLIENT,
            text=text,
        )
        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.CLIENT_MESSAGE_ADDED,
            payload_json=build_message_payload(
                telegram_message_id=telegram_message_id,
                sender_type=TicketMessageSenderType.CLIENT,
                sender_operator_id=None,
            ),
        )

        return build_ticket_summary(
            queued_ticket,
            created=True,
            event_type=TicketEventType.QUEUED,
        )


class AddMessageToTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_message_repository: TicketMessageRepository,
        ticket_event_repository: TicketEventRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_message_repository = ticket_message_repository
        self.ticket_event_repository = ticket_event_repository

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

        ensure_message_addable(ticket.status)
        if sender_type == TicketMessageSenderType.OPERATOR and ticket.first_response_at is None:
            ticket.first_response_at = utcnow()

        await self.ticket_message_repository.add(
            ticket_id=ticket.id,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            text=text,
            sender_operator_id=sender_operator_id,
        )

        event_type = build_event_type_for_message(sender_type)
        if event_type is not None:
            await self.ticket_event_repository.add(
                ticket_id=ticket.id,
                event_type=event_type,
                payload_json=build_message_payload(
                    telegram_message_id=telegram_message_id,
                    sender_type=sender_type,
                    sender_operator_id=sender_operator_id,
                ),
            )

        return build_ticket_summary(ticket, event_type=event_type)


class AssignTicketToOperatorUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_event_repository: TicketEventRepository,
        operator_repository: OperatorRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_event_repository = ticket_event_repository
        self.operator_repository = operator_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        ensure_assignable(ticket.status)
        operator_id = await self.operator_repository.get_or_create(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )

        previous_status = ticket.status
        previous_operator_id = ticket.assigned_operator_id
        if previous_status == TicketStatus.ASSIGNED and previous_operator_id == operator_id:
            raise InvalidTicketTransitionError("Ticket is already assigned to this operator.")

        event_type = TicketEventType.ASSIGNED
        if previous_operator_id is not None and previous_operator_id != operator_id:
            event_type = TicketEventType.REASSIGNED

        assigned_ticket = await self.ticket_repository.assign_to_operator(
            ticket_public_id=ticket_public_id,
            operator_id=operator_id,
        )
        if assigned_ticket is None:
            return None

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=event_type,
            payload_json=build_status_payload(
                from_status=previous_status,
                to_status=assigned_ticket.status,
                assigned_operator_id=operator_id,
                previous_operator_id=previous_operator_id,
                actor_operator_id=operator_id,
            ),
        )

        return build_ticket_summary(assigned_ticket, event_type=event_type)


class EscalateTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_event_repository: TicketEventRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_event_repository = ticket_event_repository

    async def __call__(self, *, ticket_public_id: UUID) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        ensure_escalatable(ticket.status)
        previous_status = ticket.status

        escalated_ticket = await self.ticket_repository.escalate(ticket_public_id=ticket_public_id)
        if escalated_ticket is None:
            return None

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.ESCALATED,
            payload_json=build_status_payload(
                from_status=previous_status,
                to_status=escalated_ticket.status,
                assigned_operator_id=escalated_ticket.assigned_operator_id,
            ),
        )

        return build_ticket_summary(escalated_ticket, event_type=TicketEventType.ESCALATED)


class CloseTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_event_repository: TicketEventRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_event_repository = ticket_event_repository

    async def __call__(self, *, ticket_public_id: UUID) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        ensure_closable(ticket.status)
        previous_status = ticket.status

        closed_ticket = await self.ticket_repository.close(ticket_public_id=ticket_public_id)
        if closed_ticket is None:
            return None

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.CLOSED,
            payload_json=build_status_payload(
                from_status=previous_status,
                to_status=closed_ticket.status,
                assigned_operator_id=closed_ticket.assigned_operator_id,
            ),
        )

        return build_ticket_summary(closed_ticket, event_type=TicketEventType.CLOSED)


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
