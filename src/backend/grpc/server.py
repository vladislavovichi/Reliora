# mypy: disable-error-code="attr-defined,name-defined,no-untyped-def"
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from uuid import UUID

import grpc

from application.contracts.actors import RequestActor
from application.services.helpdesk.service import HelpdeskServiceFactory
from application.services.stats import AnalyticsWindow
from application.use_cases.analytics.exports import AnalyticsExportFormat, AnalyticsSection
from application.use_cases.tickets.exports import TicketReportFormat
from backend.grpc.auth import BackendRequestContext, resolve_backend_request_context
from backend.grpc.generated import helpdesk_pb2, helpdesk_pb2_grpc
from backend.grpc.translators import (
    deserialize_apply_macro_command,
    deserialize_assign_next_command,
    deserialize_client_ticket_message_command,
    deserialize_operator_reply_command,
    deserialize_predict_ticket_category_command,
    deserialize_request_actor,
    deserialize_ticket_assignment_command,
    serialize_analytics_export,
    serialize_analytics_snapshot,
    serialize_archived_ticket,
    serialize_category,
    serialize_export,
    serialize_macro,
    serialize_macro_application_result,
    serialize_operator_reply_result,
    serialize_operator_ticket,
    serialize_queued_ticket,
    serialize_ticket_assist_snapshot,
    serialize_ticket_category_prediction,
    serialize_ticket_details,
    serialize_ticket_summary,
)
from domain.tickets import InvalidTicketTransitionError
from infrastructure.config.settings import BackendAuthConfig
from infrastructure.runtime_context import bind_correlation_id, reset_correlation_id

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HelpdeskBackendGrpcService(helpdesk_pb2_grpc.HelpdeskBackendServiceServicer):
    helpdesk_service_factory: HelpdeskServiceFactory
    auth_config: BackendAuthConfig

    @asynccontextmanager
    async def _rpc_scope(
        self,
        context: grpc.aio.ServicerContext,
        *,
        method: str,
        fallback_actor: RequestActor | None = None,
    ) -> AsyncIterator[BackendRequestContext]:
        try:
            request_context = resolve_backend_request_context(
                context,
                auth_config=self.auth_config,
                fallback_actor=fallback_actor,
            )
        except Exception as exc:
            await _abort_for_exception(context, exc, method=method)
            raise RuntimeError("unreachable") from exc
        correlation_token = bind_correlation_id(request_context.correlation_id)
        started_at = perf_counter()
        logger.info(
            "gRPC request started method=%s caller=%s peer=%s actor_id=%s",
            method,
            request_context.caller,
            context.peer(),
            request_context.actor.telegram_user_id if request_context.actor is not None else None,
        )
        try:
            yield request_context
            logger.info(
                "gRPC request completed method=%s caller=%s duration_ms=%s",
                method,
                request_context.caller,
                round((perf_counter() - started_at) * 1000, 2),
            )
        finally:
            reset_correlation_id(correlation_token)

    async def GetBackendStatus(
        self,
        request: helpdesk_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.BackendStatus:
        del request
        async with self._rpc_scope(context, method="GetBackendStatus"):
            return helpdesk_pb2.BackendStatus(service="helpdesk-backend", status="ready")

    async def GetClientActiveTicket(
        self,
        request: helpdesk_pb2.GetClientActiveTicketRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        async with self._rpc_scope(context, method="GetClientActiveTicket"):
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    ticket = await helpdesk_service.get_client_active_ticket(
                        client_chat_id=request.client_chat_id
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="GetClientActiveTicket")

        if ticket is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, "Активная заявка не найдена.")
        assert ticket is not None
        return serialize_ticket_summary(ticket)

    async def ListClientTicketCategories(
        self,
        request: helpdesk_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ):
        del request
        async with self._rpc_scope(context, method="ListClientTicketCategories"):
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    categories = await helpdesk_service.list_client_ticket_categories()
            except Exception as exc:
                await _abort_for_exception(context, exc, method="ListClientTicketCategories")

            for category in categories:
                yield serialize_category(category)

    async def CreateTicketFromClientMessage(
        self,
        request: helpdesk_pb2.CreateTicketFromClientMessageRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        async with self._rpc_scope(context, method="CreateTicketFromClientMessage"):
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    result = await helpdesk_service.create_ticket_from_client_message(
                        deserialize_client_ticket_message_command(request.command)
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="CreateTicketFromClientMessage")

            return serialize_ticket_summary(result)

    async def CreateTicketFromClientIntake(
        self,
        request: helpdesk_pb2.CreateTicketFromClientIntakeRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        async with self._rpc_scope(context, method="CreateTicketFromClientIntake"):
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    result = await helpdesk_service.create_ticket_from_client_intake(
                        deserialize_client_ticket_message_command(request.command)
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="CreateTicketFromClientIntake")

            return serialize_ticket_summary(result)

    async def GetTicketDetails(
        self,
        request: helpdesk_pb2.GetTicketDetailsRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketDetailsSummary:
        async with self._rpc_scope(
            context,
            method="GetTicketDetails",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    details = await helpdesk_service.get_ticket_details(
                        ticket_public_id=UUID(request.ticket_public_id),
                        actor=request_context.actor,
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="GetTicketDetails")

            if details is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Заявка не найдена.")
            assert details is not None
            return serialize_ticket_details(details)

    async def ListQueuedTickets(
        self,
        request: helpdesk_pb2.ListQueuedTicketsRequest,
        context: grpc.aio.ServicerContext,
    ):
        async with self._rpc_scope(
            context,
            method="ListQueuedTickets",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    tickets = await helpdesk_service.list_queued_tickets(
                        actor=request_context.actor
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="ListQueuedTickets")

            for ticket in tickets:
                yield serialize_queued_ticket(ticket)

    async def ListOperatorTickets(
        self,
        request: helpdesk_pb2.ListOperatorTicketsRequest,
        context: grpc.aio.ServicerContext,
    ):
        async with self._rpc_scope(
            context,
            method="ListOperatorTickets",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    tickets = await helpdesk_service.list_operator_tickets(
                        operator_telegram_user_id=request.operator_telegram_user_id,
                        actor=request_context.actor,
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="ListOperatorTickets")

            for ticket in tickets:
                yield serialize_operator_ticket(ticket)

    async def ListArchivedTickets(
        self,
        request: helpdesk_pb2.ListArchivedTicketsRequest,
        context: grpc.aio.ServicerContext,
    ):
        async with self._rpc_scope(
            context,
            method="ListArchivedTickets",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    tickets = await helpdesk_service.list_archived_tickets(
                        actor=request_context.actor
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="ListArchivedTickets")

            for ticket in tickets:
                yield serialize_archived_ticket(ticket)

    async def AssignNextQueuedTicket(
        self,
        request: helpdesk_pb2.AssignNextQueuedTicketRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        async with self._rpc_scope(
            context,
            method="AssignNextQueuedTicket",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    ticket = await helpdesk_service.assign_next_ticket_to_operator(
                        deserialize_assign_next_command(request.command),
                        actor=request_context.actor,
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="AssignNextQueuedTicket")

            if ticket is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Заявка не найдена.")
            assert ticket is not None
            return serialize_ticket_summary(ticket)

    async def AssignTicketToOperator(
        self,
        request: helpdesk_pb2.AssignTicketToOperatorRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        async with self._rpc_scope(
            context,
            method="AssignTicketToOperator",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    ticket = await helpdesk_service.assign_ticket_to_operator(
                        deserialize_ticket_assignment_command(request.command),
                        actor=request_context.actor,
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="AssignTicketToOperator")

            if ticket is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Заявка не найдена.")
            assert ticket is not None
            return serialize_ticket_summary(ticket)

    async def CloseTicket(
        self,
        request: helpdesk_pb2.CloseTicketRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        async with self._rpc_scope(
            context,
            method="CloseTicket",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    ticket = await helpdesk_service.close_ticket(
                        ticket_public_id=UUID(request.ticket_public_id),
                        actor=request_context.actor,
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="CloseTicket")

            if ticket is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Заявка не найдена.")
            assert ticket is not None
            return serialize_ticket_summary(ticket)

    async def CloseTicketAsOperator(
        self,
        request: helpdesk_pb2.CloseTicketAsOperatorRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketSummary:
        async with self._rpc_scope(
            context,
            method="CloseTicketAsOperator",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    ticket = await helpdesk_service.close_ticket_as_operator(
                        ticket_public_id=UUID(request.ticket_public_id),
                        actor=request_context.actor,
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="CloseTicketAsOperator")

            if ticket is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Заявка не найдена.")
            assert ticket is not None
            return serialize_ticket_summary(ticket)

    async def ReplyToTicketAsOperator(
        self,
        request: helpdesk_pb2.ReplyToTicketAsOperatorRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.OperatorReplyResult:
        async with self._rpc_scope(
            context,
            method="ReplyToTicketAsOperator",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    result = await helpdesk_service.reply_to_ticket_as_operator(
                        deserialize_operator_reply_command(request.command),
                        actor=request_context.actor,
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="ReplyToTicketAsOperator")

            if result is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Заявка не найдена.")
            assert result is not None
            return serialize_operator_reply_result(result)

    async def ListMacros(
        self,
        request: helpdesk_pb2.ListMacrosRequest,
        context: grpc.aio.ServicerContext,
    ):
        async with self._rpc_scope(
            context,
            method="ListMacros",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    macros = await helpdesk_service.list_macros(actor=request_context.actor)
            except Exception as exc:
                await _abort_for_exception(context, exc, method="ListMacros")

            for macro in macros:
                yield serialize_macro(macro)

    async def ApplyMacroToTicket(
        self,
        request: helpdesk_pb2.ApplyMacroToTicketRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.MacroApplicationResult:
        async with self._rpc_scope(
            context,
            method="ApplyMacroToTicket",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    result = await helpdesk_service.apply_macro_to_ticket(
                        deserialize_apply_macro_command(request.command),
                        actor=request_context.actor,
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="ApplyMacroToTicket")

            if result is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Заявка не найдена.")
            assert result is not None
            return serialize_macro_application_result(result)

    async def GetTicketAssistSnapshot(
        self,
        request: helpdesk_pb2.GetTicketAssistSnapshotRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketAssistSnapshot:
        async with self._rpc_scope(
            context,
            method="GetTicketAssistSnapshot",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    snapshot = await helpdesk_service.get_ticket_ai_assist_snapshot(
                        ticket_public_id=UUID(request.ticket_public_id),
                        refresh_summary=request.refresh_summary,
                        actor=request_context.actor,
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="GetTicketAssistSnapshot")

            if snapshot is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Заявка не найдена.")
            assert snapshot is not None
            return serialize_ticket_assist_snapshot(snapshot)

    async def PredictTicketCategory(
        self,
        request: helpdesk_pb2.PredictTicketCategoryRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketCategoryPrediction:
        async with self._rpc_scope(
            context,
            method="PredictTicketCategory",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    prediction = await helpdesk_service.predict_ticket_category(
                        deserialize_predict_ticket_category_command(request.command),
                        actor=request_context.actor,
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="PredictTicketCategory")

            return serialize_ticket_category_prediction(prediction)

    async def ExportTicketReport(
        self,
        request: helpdesk_pb2.ExportTicketReportRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketReportExport:
        async with self._rpc_scope(
            context,
            method="ExportTicketReport",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    export = await helpdesk_service.export_ticket_report(
                        ticket_public_id=UUID(request.ticket_public_id),
                        format=TicketReportFormat(request.format),
                        actor=request_context.actor,
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="ExportTicketReport")

            if export is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Заявка не найдена.")
            assert export is not None
            return serialize_export(export)

    async def GetAnalyticsSnapshot(
        self,
        request: helpdesk_pb2.GetAnalyticsSnapshotRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.HelpdeskAnalyticsSnapshot:
        async with self._rpc_scope(
            context,
            method="GetAnalyticsSnapshot",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    snapshot = await helpdesk_service.get_analytics_snapshot(
                        window=AnalyticsWindow(request.window),
                        actor=request_context.actor,
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="GetAnalyticsSnapshot")

            return serialize_analytics_snapshot(snapshot)

    async def ExportAnalyticsSnapshot(
        self,
        request: helpdesk_pb2.ExportAnalyticsSnapshotRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.AnalyticsReportExport:
        async with self._rpc_scope(
            context,
            method="ExportAnalyticsSnapshot",
            fallback_actor=_request_actor(request),
        ) as request_context:
            try:
                async with self.helpdesk_service_factory() as helpdesk_service:
                    export = await helpdesk_service.export_analytics_snapshot(
                        window=AnalyticsWindow(request.window),
                        section=AnalyticsSection(request.section),
                        format=AnalyticsExportFormat(request.format),
                        actor=request_context.actor,
                    )
            except Exception as exc:
                await _abort_for_exception(context, exc, method="ExportAnalyticsSnapshot")

            return serialize_analytics_export(export)


@dataclass(slots=True)
class HelpdeskBackendGrpcServer:
    helpdesk_service_factory: HelpdeskServiceFactory
    bind_target: str
    auth_config: BackendAuthConfig
    server: grpc.aio.Server = field(init=False)
    bound_port: int = field(init=False)

    def __post_init__(self) -> None:
        self.server = grpc.aio.server()
        helpdesk_pb2_grpc.add_HelpdeskBackendServiceServicer_to_server(
            HelpdeskBackendGrpcService(
                helpdesk_service_factory=self.helpdesk_service_factory,
                auth_config=self.auth_config,
            ),
            self.server,
        )
        self.bound_port = self.server.add_insecure_port(self.bind_target)
        if self.bound_port == 0:
            raise RuntimeError(f"Не удалось открыть gRPC порт {self.bind_target}.")

    async def start(self) -> None:
        await self.server.start()

    async def stop(self, grace: float = 5.0) -> None:
        await self.server.stop(grace)

    async def wait_for_termination(self) -> None:
        await self.server.wait_for_termination()


def build_helpdesk_backend_server(
    *,
    helpdesk_service_factory: HelpdeskServiceFactory,
    bind_target: str,
    auth_config: BackendAuthConfig,
) -> HelpdeskBackendGrpcServer:
    return HelpdeskBackendGrpcServer(
        helpdesk_service_factory=helpdesk_service_factory,
        bind_target=bind_target,
        auth_config=auth_config,
    )


async def _abort_for_exception(
    context: grpc.aio.ServicerContext,
    exc: Exception,
    *,
    method: str,
) -> None:
    level = (
        logging.WARNING
        if isinstance(exc, (InvalidTicketTransitionError, PermissionError, ValueError))
        else logging.ERROR
    )
    logger.log(
        level,
        "gRPC request failed method=%s error_type=%s error=%s",
        method,
        exc.__class__.__name__,
        exc,
        exc_info=level >= logging.ERROR,
    )
    if isinstance(exc, InvalidTicketTransitionError):
        await context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))
    if isinstance(exc, PermissionError):
        await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))
    if isinstance(exc, ValueError):
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
    await context.abort(grpc.StatusCode.INTERNAL, "Внутренняя ошибка backend сервиса.")


def _request_actor(request: Any):
    if hasattr(request, "HasField") and request.HasField("actor"):
        return deserialize_request_actor(request.actor)
    return None
