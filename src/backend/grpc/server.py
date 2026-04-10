from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.exports import TicketReportFormat
from backend.grpc.messages import (
    ApplyMacroToTicketRequest,
    AssignNextQueuedTicketRequest,
    AssignTicketToOperatorRequest,
    CloseTicketAsOperatorRequest,
    CloseTicketRequest,
    CreateTicketFromClientIntakeRequest,
    CreateTicketFromClientMessageRequest,
    ExportTicketReportRequest,
    GetAnalyticsSnapshotRequest,
    GetClientActiveTicketRequest,
    GetTicketDetailsRequest,
    HelpdeskAnalyticsSnapshotMessage,
    ListClientTicketCategoriesRequest,
    ListMacrosRequest,
    ListOperatorTicketsRequest,
    ListQueuedTicketsRequest,
    MacroApplicationResultMessage,
    MacroSummaryMessage,
    OperatorReplyResultMessage,
    OperatorTicketSummaryMessage,
    QueuedTicketSummaryMessage,
    ReplyToTicketAsOperatorRequest,
    TicketCategorySummaryMessage,
    TicketDetailsSummaryMessage,
    TicketReportExportMessage,
    TicketSummaryMessage,
)
from backend.grpc.translators import (
    deserialize_apply_macro_command,
    deserialize_assign_next_command,
    deserialize_client_ticket_message_command,
    deserialize_operator_reply_command,
    deserialize_request_actor,
    deserialize_ticket_assignment_command,
    serialize_analytics_snapshot,
    serialize_category,
    serialize_export,
    serialize_macro,
    serialize_macro_application_result,
    serialize_operator_reply_result,
    serialize_operator_ticket,
    serialize_queued_ticket,
    serialize_ticket_details,
    serialize_ticket_summary,
)


@dataclass(slots=True)
class LocalHelpdeskGrpcServer:
    helpdesk_service_factory: HelpdeskServiceFactory

    async def get_client_active_ticket(
        self,
        request: GetClientActiveTicketRequest,
    ) -> TicketSummaryMessage | None:
        async with self.helpdesk_service_factory() as helpdesk_service:
            ticket = await helpdesk_service.get_client_active_ticket(
                client_chat_id=request.client_chat_id
            )
        return None if ticket is None else serialize_ticket_summary(ticket)

    async def list_client_ticket_categories(
        self,
        request: ListClientTicketCategoriesRequest,
    ) -> tuple[TicketCategorySummaryMessage, ...]:
        del request
        async with self.helpdesk_service_factory() as helpdesk_service:
            categories = await helpdesk_service.list_client_ticket_categories()
        return tuple(serialize_category(item) for item in categories)

    async def create_ticket_from_client_message(
        self,
        request: CreateTicketFromClientMessageRequest,
    ) -> TicketSummaryMessage:
        async with self.helpdesk_service_factory() as helpdesk_service:
            result = await helpdesk_service.create_ticket_from_client_message(
                deserialize_client_ticket_message_command(request.command)
            )
        return serialize_ticket_summary(result)

    async def create_ticket_from_client_intake(
        self,
        request: CreateTicketFromClientIntakeRequest,
    ) -> TicketSummaryMessage:
        async with self.helpdesk_service_factory() as helpdesk_service:
            result = await helpdesk_service.create_ticket_from_client_intake(
                deserialize_client_ticket_message_command(request.command)
            )
        return serialize_ticket_summary(result)

    async def get_ticket_details(
        self,
        request: GetTicketDetailsRequest,
    ) -> TicketDetailsSummaryMessage | None:
        async with self.helpdesk_service_factory() as helpdesk_service:
            details = await helpdesk_service.get_ticket_details(
                ticket_public_id=UUID(request.ticket_public_id),
                actor=deserialize_request_actor(request.actor),
            )
        return None if details is None else serialize_ticket_details(details)

    async def list_queued_tickets(
        self,
        request: ListQueuedTicketsRequest,
    ) -> tuple[QueuedTicketSummaryMessage, ...]:
        async with self.helpdesk_service_factory() as helpdesk_service:
            tickets = await helpdesk_service.list_queued_tickets(
                actor=deserialize_request_actor(request.actor)
            )
        return tuple(serialize_queued_ticket(item) for item in tickets)

    async def list_operator_tickets(
        self,
        request: ListOperatorTicketsRequest,
    ) -> tuple[OperatorTicketSummaryMessage, ...]:
        async with self.helpdesk_service_factory() as helpdesk_service:
            tickets = await helpdesk_service.list_operator_tickets(
                operator_telegram_user_id=request.operator_telegram_user_id,
                actor=deserialize_request_actor(request.actor),
            )
        return tuple(serialize_operator_ticket(item) for item in tickets)

    async def assign_next_ticket_to_operator(
        self,
        request: AssignNextQueuedTicketRequest,
    ) -> TicketSummaryMessage | None:
        async with self.helpdesk_service_factory() as helpdesk_service:
            ticket = await helpdesk_service.assign_next_ticket_to_operator(
                deserialize_assign_next_command(request.command),
                actor=deserialize_request_actor(request.actor),
            )
        return None if ticket is None else serialize_ticket_summary(ticket)

    async def assign_ticket_to_operator(
        self,
        request: AssignTicketToOperatorRequest,
    ) -> TicketSummaryMessage | None:
        async with self.helpdesk_service_factory() as helpdesk_service:
            ticket = await helpdesk_service.assign_ticket_to_operator(
                deserialize_ticket_assignment_command(request.command),
                actor=deserialize_request_actor(request.actor),
            )
        return None if ticket is None else serialize_ticket_summary(ticket)

    async def close_ticket(self, request: CloseTicketRequest) -> TicketSummaryMessage | None:
        async with self.helpdesk_service_factory() as helpdesk_service:
            ticket = await helpdesk_service.close_ticket(
                ticket_public_id=UUID(request.ticket_public_id)
            )
        return None if ticket is None else serialize_ticket_summary(ticket)

    async def close_ticket_as_operator(
        self,
        request: CloseTicketAsOperatorRequest,
    ) -> TicketSummaryMessage | None:
        async with self.helpdesk_service_factory() as helpdesk_service:
            ticket = await helpdesk_service.close_ticket_as_operator(
                ticket_public_id=UUID(request.ticket_public_id),
                actor=deserialize_request_actor(request.actor),
            )
        return None if ticket is None else serialize_ticket_summary(ticket)

    async def reply_to_ticket_as_operator(
        self,
        request: ReplyToTicketAsOperatorRequest,
    ) -> OperatorReplyResultMessage | None:
        async with self.helpdesk_service_factory() as helpdesk_service:
            result = await helpdesk_service.reply_to_ticket_as_operator(
                deserialize_operator_reply_command(request.command),
                actor=deserialize_request_actor(request.actor),
            )
        return None if result is None else serialize_operator_reply_result(result)

    async def list_macros(
        self,
        request: ListMacrosRequest,
    ) -> tuple[MacroSummaryMessage, ...]:
        async with self.helpdesk_service_factory() as helpdesk_service:
            macros = await helpdesk_service.list_macros(
                actor=deserialize_request_actor(request.actor)
            )
        return tuple(serialize_macro(item) for item in macros)

    async def apply_macro_to_ticket(
        self,
        request: ApplyMacroToTicketRequest,
    ) -> MacroApplicationResultMessage | None:
        async with self.helpdesk_service_factory() as helpdesk_service:
            result = await helpdesk_service.apply_macro_to_ticket(
                deserialize_apply_macro_command(request.command),
                actor=deserialize_request_actor(request.actor),
            )
        return None if result is None else serialize_macro_application_result(result)

    async def export_ticket_report(
        self,
        request: ExportTicketReportRequest,
    ) -> TicketReportExportMessage | None:
        async with self.helpdesk_service_factory() as helpdesk_service:
            export = await helpdesk_service.export_ticket_report(
                ticket_public_id=UUID(request.ticket_public_id),
                format=TicketReportFormat(request.format),
                actor=deserialize_request_actor(request.actor),
            )
        return None if export is None else serialize_export(export)

    async def get_analytics_snapshot(
        self,
        request: GetAnalyticsSnapshotRequest,
    ) -> HelpdeskAnalyticsSnapshotMessage:
        from application.services.stats import AnalyticsWindow

        async with self.helpdesk_service_factory() as helpdesk_service:
            snapshot = await helpdesk_service.get_analytics_snapshot(
                window=AnalyticsWindow(request.window),
                actor=deserialize_request_actor(request.actor),
            )
        return serialize_analytics_snapshot(snapshot)
