# mypy: disable-error-code="attr-defined,name-defined"
from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import grpc

from backend.grpc.generated import helpdesk_pb2
from backend.grpc.server_base import HelpdeskBackendGrpcServiceBase
from backend.grpc.translators import (
    deserialize_add_internal_note_command,
    deserialize_assign_next_command,
    deserialize_client_ticket_message_command,
    deserialize_operator_reply_command,
    deserialize_ticket_assignment_command,
    serialize_access_context,
    serialize_archived_ticket,
    serialize_category,
    serialize_operator_reply_result,
    serialize_operator_ticket,
    serialize_queued_ticket,
    serialize_ticket_details,
    serialize_ticket_summary,
)


class HelpdeskBackendTicketingGrpcMixin(HelpdeskBackendGrpcServiceBase):
    async def GetBackendStatus(
        self,
        request: helpdesk_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.BackendStatus:
        del request
        async with self._rpc_scope(context, method="GetBackendStatus"):
            return helpdesk_pb2.BackendStatus(service="helpdesk-backend", status="ready")

    async def GetAccessContext(
        self,
        request: helpdesk_pb2.GetAccessContextRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.AccessContextSummary:
        return await self._unary_rpc(
            context,
            method="GetAccessContext",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.get_access_context(
                actor=request_context.actor
            ),
            serialize=serialize_access_context,
        )

    async def GetClientActiveTicket(
        self,
        request: helpdesk_pb2.GetClientActiveTicketRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        return await self._optional_unary_rpc(
            context,
            method="GetClientActiveTicket",
            call=lambda helpdesk_service, _: helpdesk_service.get_client_active_ticket(
                client_chat_id=request.client_chat_id
            ),
            serialize=serialize_ticket_summary,
            not_found_message="Активная заявка не найдена.",
        )

    async def ListClientTicketCategories(
        self,
        request: helpdesk_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[helpdesk_pb2.TicketCategorySummary]:
        del request
        async for category in self._stream_rpc(
            context,
            method="ListClientTicketCategories",
            call=lambda helpdesk_service, _: helpdesk_service.list_client_ticket_categories(),
            serialize=serialize_category,
        ):
            yield category

    async def CreateTicketFromClientMessage(
        self,
        request: helpdesk_pb2.CreateTicketFromClientMessageRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        return await self._unary_rpc(
            context,
            method="CreateTicketFromClientMessage",
            call=lambda helpdesk_service, _: helpdesk_service.create_ticket_from_client_message(
                deserialize_client_ticket_message_command(request.command)
            ),
            serialize=serialize_ticket_summary,
        )

    async def CreateTicketFromClientIntake(
        self,
        request: helpdesk_pb2.CreateTicketFromClientIntakeRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        return await self._unary_rpc(
            context,
            method="CreateTicketFromClientIntake",
            call=lambda helpdesk_service, _: helpdesk_service.create_ticket_from_client_intake(
                deserialize_client_ticket_message_command(request.command)
            ),
            serialize=serialize_ticket_summary,
        )

    async def GetTicketDetails(
        self,
        request: helpdesk_pb2.GetTicketDetailsRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketDetailsSummary:
        return await self._optional_unary_rpc(
            context,
            method="GetTicketDetails",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.get_ticket_details(
                ticket_public_id=UUID(request.ticket_public_id),
                actor=request_context.actor,
            ),
            serialize=serialize_ticket_details,
            not_found_message="Заявка не найдена.",
        )

    async def ListQueuedTickets(
        self,
        request: helpdesk_pb2.ListQueuedTicketsRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[helpdesk_pb2.QueuedTicketSummary]:
        async for ticket in self._stream_rpc(
            context,
            method="ListQueuedTickets",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.list_queued_tickets(
                actor=request_context.actor
            ),
            serialize=serialize_queued_ticket,
        ):
            yield ticket

    async def ListOperatorTickets(
        self,
        request: helpdesk_pb2.ListOperatorTicketsRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[helpdesk_pb2.OperatorTicketSummary]:
        async for ticket in self._stream_rpc(
            context,
            method="ListOperatorTickets",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.list_operator_tickets(
                operator_telegram_user_id=request.operator_telegram_user_id,
                actor=request_context.actor,
            ),
            serialize=serialize_operator_ticket,
        ):
            yield ticket

    async def ListArchivedTickets(
        self,
        request: helpdesk_pb2.ListArchivedTicketsRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[helpdesk_pb2.ArchivedTicketSummary]:
        async for ticket in self._stream_rpc(
            context,
            method="ListArchivedTickets",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.list_archived_tickets(
                actor=request_context.actor
            ),
            serialize=serialize_archived_ticket,
        ):
            yield ticket

    async def AssignNextQueuedTicket(
        self,
        request: helpdesk_pb2.AssignNextQueuedTicketRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        return await self._optional_unary_rpc(
            context,
            method="AssignNextQueuedTicket",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: (
                helpdesk_service.assign_next_ticket_to_operator(
                    deserialize_assign_next_command(request.command),
                    actor=request_context.actor,
                )
            ),
            serialize=serialize_ticket_summary,
            not_found_message="Заявка не найдена.",
        )

    async def AssignTicketToOperator(
        self,
        request: helpdesk_pb2.AssignTicketToOperatorRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        return await self._optional_unary_rpc(
            context,
            method="AssignTicketToOperator",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: (
                helpdesk_service.assign_ticket_to_operator(
                    deserialize_ticket_assignment_command(request.command),
                    actor=request_context.actor,
                )
            ),
            serialize=serialize_ticket_summary,
            not_found_message="Заявка не найдена.",
        )

    async def CloseTicket(
        self,
        request: helpdesk_pb2.CloseTicketRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        return await self._optional_unary_rpc(
            context,
            method="CloseTicket",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.close_ticket(
                ticket_public_id=UUID(request.ticket_public_id),
                actor=request_context.actor,
            ),
            serialize=serialize_ticket_summary,
            not_found_message="Заявка не найдена.",
        )

    async def CloseTicketAsOperator(
        self,
        request: helpdesk_pb2.CloseTicketAsOperatorRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        return await self._optional_unary_rpc(
            context,
            method="CloseTicketAsOperator",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: (
                helpdesk_service.close_ticket_as_operator(
                    ticket_public_id=UUID(request.ticket_public_id),
                    actor=request_context.actor,
                )
            ),
            serialize=serialize_ticket_summary,
            not_found_message="Заявка не найдена.",
        )

    async def CloseTicketAsClient(
        self,
        request: helpdesk_pb2.CloseTicketAsClientRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        return await self._optional_unary_rpc(
            context,
            method="CloseTicketAsClient",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: (
                helpdesk_service.close_ticket_as_client(
                    ticket_public_id=UUID(request.ticket_public_id),
                    actor=request_context.actor,
                )
            ),
            serialize=serialize_ticket_summary,
            not_found_message="Заявка не найдена.",
        )

    async def EscalateTicketAsOperator(
        self,
        request: helpdesk_pb2.EscalateTicketAsOperatorRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        return await self._optional_unary_rpc(
            context,
            method="EscalateTicketAsOperator",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: (
                helpdesk_service.escalate_ticket_as_operator(
                    ticket_public_id=UUID(request.ticket_public_id),
                    actor=request_context.actor,
                )
            ),
            serialize=serialize_ticket_summary,
            not_found_message="Заявка не найдена.",
        )

    async def ReplyToTicketAsOperator(
        self,
        request: helpdesk_pb2.ReplyToTicketAsOperatorRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.OperatorReplyResult:
        return await self._optional_unary_rpc(
            context,
            method="ReplyToTicketAsOperator",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: (
                helpdesk_service.reply_to_ticket_as_operator(
                    deserialize_operator_reply_command(request.command),
                    actor=request_context.actor,
                )
            ),
            serialize=serialize_operator_reply_result,
            not_found_message="Заявка не найдена.",
        )

    async def AddInternalNoteToTicket(
        self,
        request: helpdesk_pb2.AddInternalNoteToTicketRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        return await self._optional_unary_rpc(
            context,
            method="AddInternalNoteToTicket",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: (
                helpdesk_service.add_internal_note_to_ticket(
                    deserialize_add_internal_note_command(request.command),
                    actor=request_context.actor,
                )
            ),
            serialize=serialize_ticket_summary,
            not_found_message="Заявка не найдена.",
        )
