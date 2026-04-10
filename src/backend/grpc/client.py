from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from application.contracts.actors import RequestActor
from application.contracts.tickets import (
    ApplyMacroToTicketCommand,
    AssignNextQueuedTicketCommand,
    ClientTicketMessageCommand,
    OperatorTicketReplyCommand,
    TicketAssignmentCommand,
)
from application.services.stats import AnalyticsWindow, HelpdeskAnalyticsSnapshot
from application.use_cases.tickets.exports import TicketReportExport, TicketReportFormat
from application.use_cases.tickets.summaries import (
    MacroApplicationResult,
    MacroSummary,
    OperatorReplyResult,
    OperatorTicketSummary,
    QueuedTicketSummary,
    TicketCategorySummary,
    TicketDetailsSummary,
    TicketSummary,
)
from backend.grpc.contracts import HelpdeskBackendClient
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
    ListClientTicketCategoriesRequest,
    ListMacrosRequest,
    ListOperatorTicketsRequest,
    ListQueuedTicketsRequest,
    ReplyToTicketAsOperatorRequest,
)
from backend.grpc.server import LocalHelpdeskGrpcServer
from backend.grpc.translators import (
    deserialize_analytics_snapshot,
    deserialize_category,
    deserialize_export,
    deserialize_macro,
    deserialize_macro_application_result,
    deserialize_operator_reply_result,
    deserialize_operator_ticket,
    deserialize_queued_ticket,
    deserialize_ticket_details,
    deserialize_ticket_summary,
    serialize_apply_macro_command,
    serialize_assign_next_command,
    serialize_client_ticket_message_command,
    serialize_operator_reply_command,
    serialize_request_actor,
    serialize_ticket_assignment_command,
)


@dataclass(slots=True)
class LocalHelpdeskGrpcClient(HelpdeskBackendClient):
    server: LocalHelpdeskGrpcServer

    async def get_client_active_ticket(self, *, client_chat_id: int) -> TicketSummary | None:
        result = await self.server.get_client_active_ticket(
            GetClientActiveTicketRequest(client_chat_id=client_chat_id)
        )
        return None if result is None else deserialize_ticket_summary(result)

    async def list_client_ticket_categories(self) -> tuple[TicketCategorySummary, ...]:
        result = await self.server.list_client_ticket_categories(
            ListClientTicketCategoriesRequest()
        )
        return tuple(deserialize_category(item) for item in result)

    async def create_ticket_from_client_message(
        self,
        command: ClientTicketMessageCommand,
    ) -> TicketSummary:
        result = await self.server.create_ticket_from_client_message(
            CreateTicketFromClientMessageRequest(
                command=serialize_client_ticket_message_command(command)
            )
        )
        return deserialize_ticket_summary(result)

    async def create_ticket_from_client_intake(
        self,
        command: ClientTicketMessageCommand,
    ) -> TicketSummary:
        result = await self.server.create_ticket_from_client_intake(
            CreateTicketFromClientIntakeRequest(
                command=serialize_client_ticket_message_command(command)
            )
        )
        return deserialize_ticket_summary(result)

    async def get_ticket_details(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketDetailsSummary | None:
        result = await self.server.get_ticket_details(
            GetTicketDetailsRequest(
                ticket_public_id=str(ticket_public_id),
                actor=serialize_request_actor(actor),
            )
        )
        return None if result is None else deserialize_ticket_details(result)

    async def list_queued_tickets(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> tuple[QueuedTicketSummary, ...]:
        result = await self.server.list_queued_tickets(
            ListQueuedTicketsRequest(actor=serialize_request_actor(actor))
        )
        return tuple(deserialize_queued_ticket(item) for item in result)

    async def list_operator_tickets(
        self,
        *,
        operator_telegram_user_id: int,
        actor: RequestActor | None = None,
    ) -> tuple[OperatorTicketSummary, ...]:
        result = await self.server.list_operator_tickets(
            ListOperatorTicketsRequest(
                operator_telegram_user_id=operator_telegram_user_id,
                actor=serialize_request_actor(actor),
            )
        )
        return tuple(deserialize_operator_ticket(item) for item in result)

    async def assign_next_ticket_to_operator(
        self,
        command: AssignNextQueuedTicketCommand,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        result = await self.server.assign_next_ticket_to_operator(
            AssignNextQueuedTicketRequest(
                command=serialize_assign_next_command(command),
                actor=serialize_request_actor(actor),
            )
        )
        return None if result is None else deserialize_ticket_summary(result)

    async def assign_ticket_to_operator(
        self,
        command: TicketAssignmentCommand,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        result = await self.server.assign_ticket_to_operator(
            AssignTicketToOperatorRequest(
                command=serialize_ticket_assignment_command(command),
                actor=serialize_request_actor(actor),
            )
        )
        return None if result is None else deserialize_ticket_summary(result)

    async def close_ticket(
        self,
        *,
        ticket_public_id: UUID,
    ) -> TicketSummary | None:
        result = await self.server.close_ticket(
            CloseTicketRequest(ticket_public_id=str(ticket_public_id))
        )
        return None if result is None else deserialize_ticket_summary(result)

    async def close_ticket_as_operator(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None,
    ) -> TicketSummary | None:
        result = await self.server.close_ticket_as_operator(
            CloseTicketAsOperatorRequest(
                ticket_public_id=str(ticket_public_id),
                actor=serialize_request_actor(actor),
            )
        )
        return None if result is None else deserialize_ticket_summary(result)

    async def reply_to_ticket_as_operator(
        self,
        command: OperatorTicketReplyCommand,
        actor: RequestActor | None = None,
    ) -> OperatorReplyResult | None:
        result = await self.server.reply_to_ticket_as_operator(
            ReplyToTicketAsOperatorRequest(
                command=serialize_operator_reply_command(command),
                actor=serialize_request_actor(actor),
            )
        )
        return None if result is None else deserialize_operator_reply_result(result)

    async def list_macros(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> tuple[MacroSummary, ...]:
        result = await self.server.list_macros(
            ListMacrosRequest(actor=serialize_request_actor(actor))
        )
        return tuple(deserialize_macro(item) for item in result)

    async def apply_macro_to_ticket(
        self,
        command: ApplyMacroToTicketCommand,
        actor: RequestActor | None = None,
    ) -> MacroApplicationResult | None:
        result = await self.server.apply_macro_to_ticket(
            ApplyMacroToTicketRequest(
                command=serialize_apply_macro_command(command),
                actor=serialize_request_actor(actor),
            )
        )
        return None if result is None else deserialize_macro_application_result(result)

    async def export_ticket_report(
        self,
        *,
        ticket_public_id: UUID,
        format: TicketReportFormat,
        actor: RequestActor | None = None,
    ) -> TicketReportExport | None:
        result = await self.server.export_ticket_report(
            ExportTicketReportRequest(
                ticket_public_id=str(ticket_public_id),
                format=format.value,
                actor=serialize_request_actor(actor),
            )
        )
        return None if result is None else deserialize_export(result)

    async def get_analytics_snapshot(
        self,
        *,
        window: AnalyticsWindow,
        actor: RequestActor | None = None,
    ) -> HelpdeskAnalyticsSnapshot:
        result = await self.server.get_analytics_snapshot(
            GetAnalyticsSnapshotRequest(
                window=window.value,
                actor=serialize_request_actor(actor),
            )
        )
        return deserialize_analytics_snapshot(result)


@asynccontextmanager
async def provide_local_helpdesk_grpc_client(
    server: LocalHelpdeskGrpcServer,
) -> AsyncIterator[HelpdeskBackendClient]:
    yield cast(HelpdeskBackendClient, LocalHelpdeskGrpcClient(server=server))
