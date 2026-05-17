from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from aiogram import Bot
from application.contracts.actors import OperatorIdentity
from application.contracts.tickets import (
    AddInternalNoteCommand,
    ApplyMacroToTicketCommand,
    AssignNextQueuedTicketCommand,
    TicketAssignmentCommand,
)
from application.errors import NotFoundError
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.delivery import deliver_text_to_chat, deliver_ticket_closed_to_client
from bot.keyboards.inline.client_actions import build_client_ticket_markup
from bot.keyboards.inline.feedback import build_ticket_feedback_rating_markup
from mini_app.auth import TelegramMiniAppUser
from mini_app.gateway.common import build_actor, build_operator_identity
from mini_app.serializers import (
    serialize_access_context,
    serialize_archived_ticket,
    serialize_macro,
    serialize_operator,
    serialize_operator_ticket,
    serialize_queue_ticket,
    serialize_ticket_ai_snapshot,
    serialize_ticket_details,
    serialize_ticket_timeline,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MiniAppTicketsGateway:
    backend_client_factory: HelpdeskBackendClientFactory
    bot: Bot

    async def list_queue(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        actor = build_actor(user)
        async with self.backend_client_factory() as client:
            tickets = await client.list_queued_tickets(actor=actor)
        return {"items": [serialize_queue_ticket(item) for item in tickets]}

    async def take_next_ticket(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        actor = build_actor(user)
        async with self.backend_client_factory() as client:
            ticket = await client.assign_next_ticket_to_operator(
                command=AssignNextQueuedTicketCommand(
                    operator=build_operator_identity(user),
                    prioritize_priority=True,
                ),
                actor=actor,
            )
        if ticket is None:
            raise NotFoundError("Свободная заявка не найдена.")
        return {
            "ticket": {
                "public_id": str(ticket.public_id),
                "public_number": ticket.public_number,
                "status": ticket.status.value,
                "created": ticket.created,
                "event_type": ticket.event_type.value if ticket.event_type is not None else None,
            }
        }

    async def list_my_tickets(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        actor = build_actor(user)
        async with self.backend_client_factory() as client:
            tickets = await client.list_operator_tickets(
                operator_telegram_user_id=user.telegram_user_id,
                actor=actor,
            )
        return {"items": [serialize_operator_ticket(item) for item in tickets]}

    async def list_archive(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        actor = build_actor(user)
        async with self.backend_client_factory() as client:
            tickets = await client.list_archived_tickets(actor=actor)
        return {"items": [serialize_archived_ticket(item) for item in tickets]}

    async def get_ticket_workspace(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        actor = build_actor(user)
        async with self.backend_client_factory() as client:
            session = await client.get_access_context(actor=actor)
            details = await client.get_ticket_details(
                ticket_public_id=ticket_public_id,
                actor=actor,
            )
            if details is None:
                raise NotFoundError("Заявка не найдена.")
            ai_snapshot = await client.get_ticket_ai_assist_snapshot(
                ticket_public_id=ticket_public_id,
                refresh_summary=False,
                actor=actor,
            )
            macros = await client.list_macros(actor=actor)
            operators = await client.list_operators(actor=actor)

        try:
            timeline = serialize_ticket_timeline(details, ai_snapshot)
        except (TypeError, ValueError, AttributeError, KeyError):
            timeline = {
                "items": [],
                "warning": "Ticket history is temporarily unavailable.",
            }
        serialized_ai = serialize_ticket_ai_snapshot(ai_snapshot)

        return {
            "session": serialize_access_context(session),
            "ticket": serialize_ticket_details(details),
            "ai": serialized_ai,
            "timeline": timeline,
            "macros": [serialize_macro(item) for item in macros],
            "operators": [serialize_operator(item) for item in operators],
        }

    async def take_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        actor = build_actor(user)
        async with self.backend_client_factory() as client:
            ticket = await client.assign_ticket_to_operator(
                TicketAssignmentCommand(
                    ticket_public_id=ticket_public_id,
                    operator=build_operator_identity(user),
                ),
                actor=actor,
            )
        if ticket is None:
            raise NotFoundError("Заявка не найдена.")
        return {"public_id": str(ticket.public_id), "status": ticket.status.value}

    async def close_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        actor = build_actor(user)
        async with self.backend_client_factory() as client:
            ticket = await client.close_ticket_as_operator(
                ticket_public_id=ticket_public_id,
                actor=actor,
            )
            if ticket is None:
                raise NotFoundError("Заявка не найдена.")
            ticket_details = await client.get_ticket_details(
                ticket_public_id=ticket_public_id,
                actor=actor,
            )
        if ticket_details is not None:
            await deliver_ticket_closed_to_client(
                self.bot,
                chat_id=ticket_details.client_chat_id,
                public_number=ticket.public_number,
                reply_markup=build_ticket_feedback_rating_markup(ticket_public_id=ticket.public_id),
                logger=logger,
            )
        return {"public_id": str(ticket.public_id), "status": ticket.status.value}

    async def escalate_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        actor = build_actor(user)
        async with self.backend_client_factory() as client:
            ticket = await client.escalate_ticket_as_operator(
                ticket_public_id=ticket_public_id,
                actor=actor,
            )
        if ticket is None:
            raise NotFoundError("Заявка не найдена.")
        return {"public_id": str(ticket.public_id), "status": ticket.status.value}

    async def assign_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
        operator_identity: OperatorIdentity,
    ) -> dict[str, Any]:
        actor = build_actor(user)
        async with self.backend_client_factory() as client:
            ticket = await client.assign_ticket_to_operator(
                TicketAssignmentCommand(
                    ticket_public_id=ticket_public_id,
                    operator=operator_identity,
                ),
                actor=actor,
            )
        if ticket is None:
            raise NotFoundError("Заявка не найдена.")
        return {"public_id": str(ticket.public_id), "status": ticket.status.value}

    async def add_note(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
        text: str,
    ) -> dict[str, Any]:
        actor = build_actor(user)
        async with self.backend_client_factory() as client:
            ticket = await client.add_internal_note_to_ticket(
                AddInternalNoteCommand(
                    ticket_public_id=ticket_public_id,
                    author=build_operator_identity(user),
                    text=text,
                ),
                actor=actor,
            )
        if ticket is None:
            raise NotFoundError("Заявка не найдена.")
        return {"public_id": str(ticket.public_id), "status": ticket.status.value}

    async def apply_macro(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
        macro_id: int,
    ) -> dict[str, Any]:
        actor = build_actor(user)
        async with self.backend_client_factory() as client:
            result = await client.apply_macro_to_ticket(
                command=ApplyMacroToTicketCommand(
                    ticket_public_id=ticket_public_id,
                    macro_id=macro_id,
                    operator=build_operator_identity(user),
                ),
                actor=actor,
            )
        if result is None:
            raise NotFoundError("Заявка не найдена.")
        if result.ticket.event_type is not None:
            await deliver_text_to_chat(
                self.bot,
                chat_id=result.client_chat_id,
                text=result.macro.body,
                reply_markup=build_client_ticket_markup(ticket_public_id=ticket_public_id),
                logger=logger,
                operation="apply_macro",
            )
        return {
            "ticket_public_id": str(result.ticket.public_id),
            "ticket_status": result.ticket.status.value,
            "macro_id": result.macro.id,
            "macro_title": result.macro.title,
        }
