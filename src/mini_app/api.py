from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from application.contracts.actors import OperatorIdentity, RequestActor
from application.contracts.tickets import (
    AddInternalNoteCommand,
    ApplyMacroToTicketCommand,
    AssignNextQueuedTicketCommand,
    TicketAssignmentCommand,
)
from application.services.stats import AnalyticsWindow
from application.use_cases.analytics.exports import AnalyticsExportFormat, AnalyticsSection
from application.use_cases.tickets.exports import TicketReportFormat
from backend.grpc.contracts import HelpdeskBackendClientFactory
from mini_app.auth import TelegramMiniAppUser
from mini_app.serializers import (
    serialize_access_context,
    serialize_analytics_snapshot,
    serialize_archived_ticket,
    serialize_macro,
    serialize_operator,
    serialize_operator_invite,
    serialize_operator_ticket,
    serialize_queue_ticket,
    serialize_ticket_ai_snapshot,
    serialize_ticket_details,
    serialize_ticket_reply_draft,
)


@dataclass(slots=True, frozen=True)
class BinaryPayload:
    filename: str
    content_type: str
    content: bytes


@dataclass(slots=True)
class MiniAppGateway:
    backend_client_factory: HelpdeskBackendClientFactory

    async def get_session(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)

        async with self.backend_client_factory() as client:
            access_context = await client.get_access_context(actor=actor)

        return {
            "access": serialize_access_context(access_context),
            "user": {
                "telegram_user_id": user.telegram_user_id,
                "display_name": user.display_name,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "language_code": user.language_code,
            },
        }

    async def get_dashboard(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            snapshot = await client.get_analytics_snapshot(
                window=AnalyticsWindow.DAYS_7,
                actor=actor,
            )
            queued = await client.list_queued_tickets(actor=actor)
            mine = await client.list_operator_tickets(
                operator_telegram_user_id=user.telegram_user_id,
                actor=actor,
            )
            archive = await client.list_archived_tickets(actor=actor)

        mine_serialized = [serialize_operator_ticket(item) for item in mine]
        queued_serialized = [serialize_queue_ticket(item) for item in queued]
        archive_serialized = [serialize_archived_ticket(item) for item in archive[:6]]
        escalations = [item for item in mine_serialized if item["status"] == "escalated"]

        return {
            "snapshot": serialize_analytics_snapshot(snapshot),
            "queue_preview": queued_serialized[:6],
            "my_tickets_preview": mine_serialized[:6],
            "escalations": escalations[:6],
            "recent_archive": archive_serialized,
        }

    async def list_queue(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            tickets = await client.list_queued_tickets(actor=actor)
        return {"items": [serialize_queue_ticket(item) for item in tickets]}

    async def take_next_ticket(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            ticket = await client.assign_next_ticket_to_operator(
                command=self._build_assign_next_command(user),
                actor=actor,
            )
        if ticket is None:
            raise LookupError("Свободная заявка не найдена.")
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
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            tickets = await client.list_operator_tickets(
                operator_telegram_user_id=user.telegram_user_id,
                actor=actor,
            )
        return {"items": [serialize_operator_ticket(item) for item in tickets]}

    async def list_archive(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            tickets = await client.list_archived_tickets(actor=actor)
        return {"items": [serialize_archived_ticket(item) for item in tickets]}

    async def get_ticket_workspace(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            session = await client.get_access_context(actor=actor)
            details = await client.get_ticket_details(
                ticket_public_id=ticket_public_id,
                actor=actor,
            )
            if details is None:
                raise LookupError("Заявка не найдена.")
            ai_snapshot = await client.get_ticket_ai_assist_snapshot(
                ticket_public_id=ticket_public_id,
                refresh_summary=False,
                actor=actor,
            )
            macros = await client.list_macros(actor=actor)
            operators = await client.list_operators(actor=actor)

        return {
            "session": serialize_access_context(session),
            "ticket": serialize_ticket_details(details),
            "ai": serialize_ticket_ai_snapshot(ai_snapshot),
            "macros": [serialize_macro(item) for item in macros],
            "operators": [serialize_operator(item) for item in operators],
        }

    async def refresh_ticket_ai_summary(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            ai_snapshot = await client.get_ticket_ai_assist_snapshot(
                ticket_public_id=ticket_public_id,
                refresh_summary=True,
                actor=actor,
            )
        if ai_snapshot is None:
            raise LookupError("Заявка не найдена.")
        serialized = serialize_ticket_ai_snapshot(ai_snapshot)
        if serialized is None:
            raise LookupError("Заявка не найдена.")
        return serialized

    async def generate_ticket_reply_draft(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            draft = await client.generate_ticket_reply_draft(
                ticket_public_id=ticket_public_id,
                actor=actor,
            )
        if draft is None:
            raise LookupError("Заявка не найдена.")
        serialized = serialize_ticket_reply_draft(draft)
        if serialized is None:
            raise LookupError("Заявка не найдена.")
        return serialized

    async def take_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            ticket = await client.assign_ticket_to_operator(
                TicketAssignmentCommand(
                    ticket_public_id=ticket_public_id,
                    operator=self._build_operator_identity(user),
                ),
                actor=actor,
            )
        if ticket is None:
            raise LookupError("Заявка не найдена.")
        return {"public_id": str(ticket.public_id), "status": ticket.status.value}

    async def close_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            ticket = await client.close_ticket_as_operator(
                ticket_public_id=ticket_public_id,
                actor=actor,
            )
        if ticket is None:
            raise LookupError("Заявка не найдена.")
        return {"public_id": str(ticket.public_id), "status": ticket.status.value}

    async def escalate_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            ticket = await client.escalate_ticket_as_operator(
                ticket_public_id=ticket_public_id,
                actor=actor,
            )
        if ticket is None:
            raise LookupError("Заявка не найдена.")
        return {"public_id": str(ticket.public_id), "status": ticket.status.value}

    async def assign_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
        operator_identity: OperatorIdentity,
    ) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            ticket = await client.assign_ticket_to_operator(
                TicketAssignmentCommand(
                    ticket_public_id=ticket_public_id,
                    operator=operator_identity,
                ),
                actor=actor,
            )
        if ticket is None:
            raise LookupError("Заявка не найдена.")
        return {"public_id": str(ticket.public_id), "status": ticket.status.value}

    async def add_note(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
        text: str,
    ) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            ticket = await client.add_internal_note_to_ticket(
                AddInternalNoteCommand(
                    ticket_public_id=ticket_public_id,
                    author=self._build_operator_identity(user),
                    text=text,
                ),
                actor=actor,
            )
        if ticket is None:
            raise LookupError("Заявка не найдена.")
        return {"public_id": str(ticket.public_id), "status": ticket.status.value}

    async def apply_macro(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
        macro_id: int,
    ) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            result = await client.apply_macro_to_ticket(
                command=self._build_apply_macro_command(
                    ticket_public_id=ticket_public_id,
                    macro_id=macro_id,
                    user=user,
                ),
                actor=actor,
            )
        if result is None:
            raise LookupError("Заявка не найдена.")
        return {
            "ticket_public_id": str(result.ticket.public_id),
            "ticket_status": result.ticket.status.value,
            "macro_id": result.macro.id,
            "macro_title": result.macro.title,
        }

    async def get_analytics(
        self,
        *,
        user: TelegramMiniAppUser,
        window: AnalyticsWindow,
    ) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            snapshot = await client.get_analytics_snapshot(window=window, actor=actor)
        return {"snapshot": serialize_analytics_snapshot(snapshot)}

    async def export_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
        format: TicketReportFormat,
    ) -> BinaryPayload:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            export = await client.export_ticket_report(
                ticket_public_id=ticket_public_id,
                format=format,
                actor=actor,
            )
        if export is None:
            raise LookupError("Заявка не найдена.")
        return BinaryPayload(
            filename=export.filename,
            content_type=export.content_type,
            content=export.content,
        )

    async def export_analytics(
        self,
        *,
        user: TelegramMiniAppUser,
        window: AnalyticsWindow,
        section: AnalyticsSection,
        format: AnalyticsExportFormat,
    ) -> BinaryPayload:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            export = await client.export_analytics_snapshot(
                window=window,
                section=section,
                format=format,
                actor=actor,
            )
        return BinaryPayload(
            filename=export.filename,
            content_type=export.content_type,
            content=export.content,
        )

    async def list_operators(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            operators = await client.list_operators(actor=actor)
        return {"items": [serialize_operator(item) for item in operators]}

    async def create_operator_invite(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        actor = RequestActor(telegram_user_id=user.telegram_user_id)
        async with self.backend_client_factory() as client:
            invite = await client.create_operator_invite(actor=actor)
        return {"invite": serialize_operator_invite(invite)}

    def _build_operator_identity(self, user: TelegramMiniAppUser) -> OperatorIdentity:
        return OperatorIdentity(
            telegram_user_id=user.telegram_user_id,
            display_name=user.display_name,
            username=user.username,
        )

    def _build_assign_next_command(
        self,
        user: TelegramMiniAppUser,
    ) -> AssignNextQueuedTicketCommand:
        return AssignNextQueuedTicketCommand(
            operator=self._build_operator_identity(user),
            prioritize_priority=True,
        )

    def _build_apply_macro_command(
        self,
        *,
        ticket_public_id: UUID,
        macro_id: int,
        user: TelegramMiniAppUser,
    ) -> ApplyMacroToTicketCommand:
        return ApplyMacroToTicketCommand(
            ticket_public_id=ticket_public_id,
            macro_id=macro_id,
            operator=self._build_operator_identity(user),
        )
