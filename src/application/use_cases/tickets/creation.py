from __future__ import annotations

from application.use_cases.tickets.common import (
    build_message_payload,
    build_status_payload,
    build_ticket_subject,
    build_ticket_summary,
)
from application.use_cases.tickets.messaging import AddMessageToTicketUseCase
from application.use_cases.tickets.summaries import TicketSummary
from domain.contracts.repositories import (
    TicketEventRepository,
    TicketMessageRepository,
    TicketRepository,
)
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketEventType, TicketMessageSenderType, TicketStatus


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
        self._add_message_to_ticket = AddMessageToTicketUseCase(
            ticket_repository=ticket_repository,
            ticket_message_repository=ticket_message_repository,
            ticket_event_repository=ticket_event_repository,
        )

    async def __call__(
        self,
        *,
        client_chat_id: int,
        telegram_message_id: int,
        text: str | None,
        attachment: TicketAttachmentDetails | None = None,
        category_id: int | None = None,
    ) -> TicketSummary:
        active_ticket = await self.ticket_repository.get_active_by_client_chat_id(client_chat_id)
        if active_ticket is not None:
            result = await self._add_message_to_ticket(
                ticket_public_id=active_ticket.public_id,
                telegram_message_id=telegram_message_id,
                sender_type=TicketMessageSenderType.CLIENT,
                text=text,
                attachment=attachment,
            )
            if result is None:
                raise RuntimeError("Не удалось добавить сообщение в активную заявку.")
            return result

        ticket = await self.ticket_repository.create(
            client_chat_id=client_chat_id,
            subject=build_ticket_subject(text or ""),
            category_id=category_id,
        )
        if ticket.id is None:
            raise RuntimeError("Не удалось сгенерировать идентификатор заявки.")

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.CREATED,
            payload_json={
                "status": ticket.status.value,
                "subject": ticket.subject,
                "client_chat_id": ticket.client_chat_id,
                "category_id": category_id,
            },
        )

        queued_ticket = await self.ticket_repository.enqueue(ticket_public_id=ticket.public_id)
        if queued_ticket is None:
            raise RuntimeError("Не удалось поставить заявку в очередь.")

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
            attachment=attachment,
        )
        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.CLIENT_MESSAGE_ADDED,
            payload_json=build_message_payload(
                telegram_message_id=telegram_message_id,
                sender_type=TicketMessageSenderType.CLIENT,
                sender_operator_id=None,
                attachment=attachment,
            ),
        )

        return build_ticket_summary(
            queued_ticket,
            created=True,
            event_type=TicketEventType.QUEUED,
        )


class GetActiveClientTicketUseCase:
    def __init__(self, ticket_repository: TicketRepository) -> None:
        self.ticket_repository = ticket_repository

    async def __call__(self, *, client_chat_id: int) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_active_by_client_chat_id(client_chat_id)
        if ticket is None:
            return None
        return build_ticket_summary(ticket)
