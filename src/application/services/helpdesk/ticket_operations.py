from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import cast
from uuid import UUID

from application.services.authorization import Permission
from application.services.helpdesk.components import HelpdeskComponents
from application.use_cases.tickets.exports import (
    TicketReportExport,
    TicketReportFormat,
)
from application.use_cases.tickets.summaries import (
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
from infrastructure.redis.contracts import SLADeadlineScheduler


class HelpdeskTicketOperations:
    _components: HelpdeskComponents
    sla_deadline_scheduler: SLADeadlineScheduler | None
    _ensure_permission: Callable[..., Awaitable[None]]
    _require_permission_if_actor: Callable[..., Awaitable[None]]

    async def create_ticket_from_client_message(
        self,
        *,
        client_chat_id: int,
        telegram_message_id: int,
        text: str | None,
        attachment: TicketAttachmentDetails | None = None,
    ) -> TicketSummary:
        result = await self._components.tickets.create_from_client_message(
            client_chat_id=client_chat_id,
            telegram_message_id=telegram_message_id,
            text=text,
            attachment=attachment,
        )
        await cast(HelpdeskSLASync, self)._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def create_ticket_from_client_intake(
        self,
        *,
        client_chat_id: int,
        telegram_message_id: int,
        category_id: int,
        text: str | None,
        attachment: TicketAttachmentDetails | None = None,
    ) -> TicketSummary:
        result = await self._components.tickets.create_from_client_message(
            client_chat_id=client_chat_id,
            telegram_message_id=telegram_message_id,
            text=text,
            attachment=attachment,
            category_id=category_id,
        )
        await cast(HelpdeskSLASync, self)._sync_sla_deadline(ticket_public_id=result.public_id)
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
        return await self._components.tickets.submit_feedback_rating(
            ticket_public_id=ticket_public_id,
            client_chat_id=client_chat_id,
            rating=rating,
        )

    async def add_ticket_feedback_comment(
        self,
        *,
        ticket_public_id: UUID,
        client_chat_id: int,
        comment: str,
    ) -> TicketFeedbackMutationResult:
        return await self._components.tickets.add_feedback_comment(
            ticket_public_id=ticket_public_id,
            client_chat_id=client_chat_id,
            comment=comment,
        )

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
            await cast(HelpdeskSLASync, self)._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def assign_ticket_to_operator(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
        actor_telegram_user_id: int | None = None,
    ) -> TicketSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        result = await self._components.tickets.assign_ticket(
            ticket_public_id=ticket_public_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )
        if result is not None:
            await cast(HelpdeskSLASync, self)._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def close_ticket(
        self,
        *,
        ticket_public_id: UUID,
    ) -> TicketSummary | None:
        result = await self._components.tickets.close_ticket(ticket_public_id=ticket_public_id)
        if result is not None:
            await cast(HelpdeskSLASync, self)._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def close_ticket_as_operator(
        self,
        *,
        ticket_public_id: UUID,
        actor_telegram_user_id: int | None,
    ) -> TicketSummary | None:
        await self._ensure_permission(
            permission=Permission.ACCESS_OPERATOR,
            telegram_user_id=actor_telegram_user_id,
        )
        return await self.close_ticket(ticket_public_id=ticket_public_id)

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
        actor_telegram_user_id: int | None = None,
    ) -> Sequence[QueuedTicketSummary]:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.tickets.list_queued(
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
        actor_telegram_user_id: int | None = None,
    ) -> TicketSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        result = await self._components.tickets.assign_next_queued(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
            prioritize_priority=prioritize_priority,
        )
        if result is not None:
            await cast(HelpdeskSLASync, self)._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def list_operator_tickets(
        self,
        *,
        operator_telegram_user_id: int,
        limit: int | None = None,
        actor_telegram_user_id: int | None = None,
    ) -> Sequence[OperatorTicketSummary]:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.tickets.list_operator_tickets(
            operator_telegram_user_id=operator_telegram_user_id,
            limit=limit,
        )

    async def get_ticket_details(
        self,
        *,
        ticket_public_id: UUID,
        actor_telegram_user_id: int | None = None,
    ) -> TicketDetailsSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.tickets.get_details(ticket_public_id=ticket_public_id)

    async def export_ticket_report(
        self,
        *,
        ticket_public_id: UUID,
        format: TicketReportFormat,
        actor_telegram_user_id: int | None = None,
    ) -> TicketReportExport | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.tickets.export_report(
            ticket_public_id=ticket_public_id,
            format=format,
        )

    async def reply_to_ticket_as_operator(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None,
        telegram_message_id: int,
        text: str | None,
        attachment: TicketAttachmentDetails | None = None,
        actor_telegram_user_id: int | None = None,
    ) -> OperatorReplyResult | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        result = await self._components.tickets.reply_as_operator(
            ticket_public_id=ticket_public_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
            telegram_message_id=telegram_message_id,
            text=text,
            attachment=attachment,
        )
        if result is not None:
            await cast(HelpdeskSLASync, self)._sync_sla_deadline(
                ticket_public_id=result.ticket.public_id
            )
        return result

    async def add_internal_note_to_ticket(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None,
        text: str,
        actor_telegram_user_id: int | None = None,
    ) -> TicketSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        result = await self._components.tickets.add_internal_note(
            ticket_public_id=ticket_public_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
            text=text,
        )
        if result is not None:
            await cast(HelpdeskSLASync, self)._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def escalate_ticket(
        self,
        *,
        ticket_public_id: UUID,
    ) -> TicketSummary | None:
        result = await self._components.tickets.escalate_ticket(ticket_public_id=ticket_public_id)
        if result is not None:
            await cast(HelpdeskSLASync, self)._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def escalate_ticket_as_operator(
        self,
        *,
        ticket_public_id: UUID,
        actor_telegram_user_id: int | None,
    ) -> TicketSummary | None:
        await self._ensure_permission(
            permission=Permission.ACCESS_OPERATOR,
            telegram_user_id=actor_telegram_user_id,
        )
        return await self.escalate_ticket(ticket_public_id=ticket_public_id)

    async def get_basic_stats(self) -> TicketStats:
        return await self._components.tickets.basic_stats()


class HelpdeskSLASync:
    async def _sync_sla_deadline(self, *, ticket_public_id: UUID) -> None: ...
