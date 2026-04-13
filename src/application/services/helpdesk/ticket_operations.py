from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from uuid import UUID

from application.contracts.actors import RequestActor, actor_telegram_user_id
from application.contracts.runtime import SLADeadlineScheduler
from application.contracts.tickets import (
    AddInternalNoteCommand,
    AssignNextQueuedTicketCommand,
    ClientTicketMessageCommand,
    OperatorTicketReplyCommand,
    TicketAssignmentCommand,
)
from application.services.audit import AuditTrail
from application.services.authorization import Permission
from application.services.helpdesk.components import HelpdeskComponents
from application.use_cases.tickets.exports import (
    TicketReportExport,
    TicketReportFormat,
)
from application.use_cases.tickets.summaries import (
    HistoricalTicketSummary,
    OperatorReplyResult,
    OperatorTicketSummary,
    QueuedTicketSummary,
    TicketCategorySummary,
    TicketDetailsSummary,
    TicketFeedbackMutationResult,
    TicketFeedbackSummary,
    TicketStats,
    TicketSummary,
)
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketMessageSenderType


class HelpdeskSLASync:
    async def _sync_sla_deadline(self, *, ticket_public_id: UUID) -> None: ...


class HelpdeskTicketOperations(HelpdeskSLASync):
    _components: HelpdeskComponents
    sla_deadline_scheduler: SLADeadlineScheduler | None
    _audit: AuditTrail
    _ensure_permission: Callable[..., Awaitable[None]]
    _require_permission_if_actor: Callable[..., Awaitable[None]]

    async def create_ticket_from_client_message(
        self,
        command: ClientTicketMessageCommand,
    ) -> TicketSummary:
        result = await self._components.tickets.create_from_client_message(command)
        await self._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def create_ticket_from_client_intake(
        self,
        command: ClientTicketMessageCommand,
    ) -> TicketSummary:
        result = await self._components.tickets.create_from_client_message(command)
        await self._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def get_client_active_ticket(self, *, client_chat_id: int) -> TicketSummary | None:
        return await self._components.tickets.get_active_client_ticket(
            client_chat_id=client_chat_id
        )

    async def get_ticket_feedback(
        self,
        *,
        ticket_public_id: UUID,
    ) -> TicketFeedbackSummary | None:
        return await self._components.tickets.get_feedback(ticket_public_id=ticket_public_id)

    async def submit_ticket_feedback_rating(
        self,
        *,
        ticket_public_id: UUID,
        client_chat_id: int,
        rating: int,
    ) -> TicketFeedbackMutationResult:
        result = await self._components.tickets.submit_feedback_rating(
            ticket_public_id=ticket_public_id,
            client_chat_id=client_chat_id,
            rating=rating,
        )
        if result.feedback is not None:
            await self._audit.write(
                action="ticket.feedback.rating",
                entity_type="ticket",
                outcome=result.status.value,
                actor_telegram_user_id=client_chat_id,
                entity_public_id=result.feedback.public_id,
                metadata={"rating": result.feedback.rating},
            )
        return result

    async def add_ticket_feedback_comment(
        self,
        *,
        ticket_public_id: UUID,
        client_chat_id: int,
        comment: str,
    ) -> TicketFeedbackMutationResult:
        result = await self._components.tickets.add_feedback_comment(
            ticket_public_id=ticket_public_id,
            client_chat_id=client_chat_id,
            comment=comment,
        )
        if result.feedback is not None:
            await self._audit.write(
                action="ticket.feedback.comment",
                entity_type="ticket",
                outcome=result.status.value,
                actor_telegram_user_id=client_chat_id,
                entity_public_id=result.feedback.public_id,
                metadata={"comment_present": bool(result.feedback.comment)},
            )
        return result

    async def list_client_ticket_categories(self) -> Sequence[TicketCategorySummary]:
        return await self._components.catalog.list_ticket_categories(include_inactive=False)

    async def add_message_to_ticket(
        self,
        *,
        ticket_public_id: UUID,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str | None,
        attachment: TicketAttachmentDetails | None = None,
        sender_operator_id: int | None = None,
    ) -> TicketSummary | None:
        result = await self._components.tickets.add_message(
            ticket_public_id=ticket_public_id,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            text=text,
            attachment=attachment,
            sender_operator_id=sender_operator_id,
        )
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def assign_ticket_to_operator(
        self,
        command: TicketAssignmentCommand,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.tickets.assign_ticket(command)
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
            await self._audit.write(
                action="ticket.assign",
                entity_type="ticket",
                outcome="applied",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_public_id=result.public_id,
                metadata={
                    "ticket_public_number": result.public_number,
                    "operator_telegram_user_id": command.operator.telegram_user_id,
                    "event_type": (
                        result.event_type.value if result.event_type is not None else None
                    ),
                },
            )
        return result

    async def close_ticket(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        result = await self._components.tickets.close_ticket(ticket_public_id=ticket_public_id)
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
            await self._audit.write(
                action="ticket.close",
                entity_type="ticket",
                outcome="applied",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_public_id=result.public_id,
                metadata={"ticket_public_number": result.public_number},
            )
        return result

    async def close_ticket_as_operator(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None,
    ) -> TicketSummary | None:
        await self._ensure_permission(
            permission=Permission.ACCESS_OPERATOR,
            telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self.close_ticket(ticket_public_id=ticket_public_id, actor=actor)

    async def get_next_queued_ticket(
        self,
        *,
        prioritize_priority: bool = False,
    ) -> QueuedTicketSummary | None:
        return await self._components.tickets.get_next_queued(
            prioritize_priority=prioritize_priority,
        )

    async def list_queued_tickets(
        self,
        *,
        limit: int | None = None,
        prioritize_priority: bool = False,
        actor: RequestActor | None = None,
    ) -> Sequence[QueuedTicketSummary]:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.tickets.list_queued(
            limit=limit,
            prioritize_priority=prioritize_priority,
        )

    async def assign_next_ticket_to_operator(
        self,
        command: AssignNextQueuedTicketCommand,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.tickets.assign_next_queued(command)
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
            await self._audit.write(
                action="ticket.take_next",
                entity_type="ticket",
                outcome="applied",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_public_id=result.public_id,
                metadata={
                    "ticket_public_number": result.public_number,
                    "operator_telegram_user_id": command.operator.telegram_user_id,
                    "prioritize_priority": command.prioritize_priority,
                },
            )
        return result

    async def list_operator_tickets(
        self,
        *,
        operator_telegram_user_id: int,
        limit: int | None = None,
        actor: RequestActor | None = None,
    ) -> Sequence[OperatorTicketSummary]:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.tickets.list_operator_tickets(
            operator_telegram_user_id=operator_telegram_user_id,
            limit=limit,
        )

    async def list_archived_tickets(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        actor: RequestActor | None = None,
    ) -> Sequence[HistoricalTicketSummary]:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.tickets.list_archived_tickets(
            limit=limit,
            offset=offset,
        )

    async def get_ticket_details(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketDetailsSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.tickets.get_details(ticket_public_id=ticket_public_id)

    async def export_ticket_report(
        self,
        *,
        ticket_public_id: UUID,
        format: TicketReportFormat,
        actor: RequestActor | None = None,
    ) -> TicketReportExport | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.tickets.export_report(
            ticket_public_id=ticket_public_id,
            format=format,
        )
        if result is not None:
            await self._audit.write(
                action="ticket.export",
                entity_type="ticket",
                outcome="generated",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_public_id=result.report.public_id,
                metadata={
                    "format": result.format.value,
                    "filename": result.filename,
                    "internal_notes_included": bool(result.report.internal_notes),
                },
            )
        return result

    async def reply_to_ticket_as_operator(
        self,
        command: OperatorTicketReplyCommand,
        actor: RequestActor | None = None,
    ) -> OperatorReplyResult | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.tickets.reply_as_operator(command)
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.ticket.public_id)
            await self._audit.write(
                action="ticket.reply",
                entity_type="ticket",
                outcome="applied",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_public_id=result.ticket.public_id,
                metadata={
                    "ticket_public_number": result.ticket.public_number,
                    "operator_telegram_user_id": command.operator.telegram_user_id,
                    "has_text": command.text is not None,
                    "has_attachment": command.attachment is not None,
                },
            )
        return result

    async def add_internal_note_to_ticket(
        self,
        command: AddInternalNoteCommand,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.tickets.add_internal_note(command)
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
            await self._audit.write(
                action="ticket.internal_note.create",
                entity_type="ticket",
                outcome="applied",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_public_id=result.public_id,
                metadata={
                    "ticket_public_number": result.public_number,
                    "author_telegram_user_id": command.author.telegram_user_id,
                },
            )
        return result

    async def escalate_ticket(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        result = await self._components.tickets.escalate_ticket(ticket_public_id=ticket_public_id)
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
            await self._audit.write(
                action="ticket.escalate",
                entity_type="ticket",
                outcome="applied",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_public_id=result.public_id,
                metadata={"ticket_public_number": result.public_number},
            )
        return result

    async def escalate_ticket_as_operator(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None,
    ) -> TicketSummary | None:
        await self._ensure_permission(
            permission=Permission.ACCESS_OPERATOR,
            telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self.escalate_ticket(ticket_public_id=ticket_public_id, actor=actor)

    async def get_basic_stats(self) -> TicketStats:
        return await self._components.tickets.basic_stats()
