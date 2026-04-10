from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from application.use_cases.tickets.common import (
    build_event_type_for_message,
    build_message_payload,
    build_ticket_summary,
    utcnow,
)
from application.use_cases.tickets.summaries import OperatorReplyResult, TicketSummary
from domain.contracts.repositories import (
    OperatorRepository,
    TicketEventRepository,
    TicketInternalNoteRepository,
    TicketMessageRepository,
    TicketRepository,
)
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketMessageSenderType
from domain.tickets import InvalidTicketTransitionError, ensure_operator_replyable


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
        text: str | None,
        attachment: TicketAttachmentDetails | None = None,
        sender_operator_id: int | None = None,
        extra_event_payload: Mapping[str, object] | None = None,
    ) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        from domain.tickets import ensure_message_addable

        if text is None and attachment is None:
            raise ValueError("Нужно передать текст сообщения или вложение.")

        ensure_message_addable(ticket.status)
        current_time = utcnow()
        if sender_type == TicketMessageSenderType.OPERATOR and ticket.first_response_at is None:
            ticket.first_response_at = current_time
        ticket.updated_at = current_time

        await self.ticket_message_repository.add(
            ticket_id=ticket.id,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            text=text,
            attachment=attachment,
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
                    attachment=attachment,
                    extra_payload=extra_event_payload,
                ),
            )

        return build_ticket_summary(ticket, event_type=event_type)


class ReplyToTicketAsOperatorUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_message_repository: TicketMessageRepository,
        ticket_event_repository: TicketEventRepository,
        operator_repository: OperatorRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.operator_repository = operator_repository
        self._add_message_to_ticket = AddMessageToTicketUseCase(
            ticket_repository=ticket_repository,
            ticket_message_repository=ticket_message_repository,
            ticket_event_repository=ticket_event_repository,
        )

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None,
        telegram_message_id: int,
        text: str | None,
        attachment: TicketAttachmentDetails | None = None,
    ) -> OperatorReplyResult | None:
        ticket_details = await self.ticket_repository.get_details_by_public_id(ticket_public_id)
        if ticket_details is None:
            return None

        ensure_operator_replyable(ticket_details.status)

        operator_id = await self.operator_repository.get_or_create(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )
        if (
            ticket_details.assigned_operator_id is not None
            and ticket_details.assigned_operator_id != operator_id
        ):
            raise InvalidTicketTransitionError("С этой заявкой уже работает другой оператор.")

        ticket = await self._add_message_to_ticket(
            ticket_public_id=ticket_public_id,
            telegram_message_id=telegram_message_id,
            sender_type=TicketMessageSenderType.OPERATOR,
            text=text,
            attachment=attachment,
            sender_operator_id=operator_id,
        )
        if ticket is None:
            return None

        return OperatorReplyResult(
            ticket=ticket,
            client_chat_id=ticket_details.client_chat_id,
        )


class AddInternalNoteToTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_internal_note_repository: TicketInternalNoteRepository,
        operator_repository: OperatorRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_internal_note_repository = ticket_internal_note_repository
        self.operator_repository = operator_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None,
        text: str,
    ) -> TicketSummary | None:
        normalized_text = text.strip()
        if not normalized_text:
            raise ValueError("Текст заметки не может быть пустым.")

        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        operator_id = await self.operator_repository.get_or_create(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )
        ticket.updated_at = utcnow()
        await self.ticket_internal_note_repository.add(
            ticket_id=ticket.id,
            author_operator_id=operator_id,
            text=normalized_text,
        )
        return build_ticket_summary(ticket)
