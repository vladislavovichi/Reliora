# mypy: disable-error-code="attr-defined,name-defined"
from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import grpc

from backend.grpc.generated import helpdesk_pb2
from backend.grpc.server_base import HelpdeskBackendGrpcServiceBase
from backend.grpc.translators import (
    deserialize_apply_macro_command,
    deserialize_predict_ticket_category_command,
    serialize_macro,
    serialize_macro_application_result,
    serialize_operator_invite_summary,
    serialize_operator_summary,
    serialize_ticket_assist_snapshot,
    serialize_ticket_category_prediction,
    serialize_ticket_reply_draft,
)


class HelpdeskBackendOperationsGrpcMixin(HelpdeskBackendGrpcServiceBase):
    async def ListOperators(
        self,
        request: helpdesk_pb2.ListOperatorsRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[helpdesk_pb2.OperatorSummary]:
        async with self._rpc_scope(
            context,
            method="ListOperators",
            fallback_actor=self._request_actor(request),
        ) as request_context:
            operators = await self._invoke_helpdesk(
                context,
                method="ListOperators",
                call=lambda helpdesk_service: helpdesk_service.list_operators(
                    actor=request_context.actor
                ),
            )
            for operator in operators:
                yield serialize_operator_summary(operator)

    async def CreateOperatorInvite(
        self,
        request: helpdesk_pb2.CreateOperatorInviteRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.OperatorInviteCodeSummary:
        async with self._rpc_scope(
            context,
            method="CreateOperatorInvite",
            fallback_actor=self._request_actor(request),
        ) as request_context:
            invite = await self._invoke_helpdesk(
                context,
                method="CreateOperatorInvite",
                call=lambda helpdesk_service: helpdesk_service.create_operator_invite(
                    actor=request_context.actor
                ),
            )
            return serialize_operator_invite_summary(invite)

    async def ListMacros(
        self,
        request: helpdesk_pb2.ListMacrosRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[helpdesk_pb2.MacroSummary]:
        async with self._rpc_scope(
            context,
            method="ListMacros",
            fallback_actor=self._request_actor(request),
        ) as request_context:
            macros = await self._invoke_helpdesk(
                context,
                method="ListMacros",
                call=lambda helpdesk_service: helpdesk_service.list_macros(
                    actor=request_context.actor
                ),
            )
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
            fallback_actor=self._request_actor(request),
        ) as request_context:
            result = await self._invoke_helpdesk(
                context,
                method="ApplyMacroToTicket",
                call=lambda helpdesk_service: helpdesk_service.apply_macro_to_ticket(
                    deserialize_apply_macro_command(request.command),
                    actor=request_context.actor,
                ),
            )
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
            fallback_actor=self._request_actor(request),
        ) as request_context:
            snapshot = await self._invoke_helpdesk(
                context,
                method="GetTicketAssistSnapshot",
                call=lambda helpdesk_service: helpdesk_service.get_ticket_ai_assist_snapshot(
                    ticket_public_id=UUID(request.ticket_public_id),
                    refresh_summary=request.refresh_summary,
                    actor=request_context.actor,
                ),
            )
            if snapshot is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Заявка не найдена.")
            assert snapshot is not None
            return serialize_ticket_assist_snapshot(snapshot)

    async def GenerateTicketReplyDraft(
        self,
        request: helpdesk_pb2.GenerateTicketReplyDraftRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketReplyDraft:
        async with self._rpc_scope(
            context,
            method="GenerateTicketReplyDraft",
            fallback_actor=self._request_actor(request),
        ) as request_context:
            draft = await self._invoke_helpdesk(
                context,
                method="GenerateTicketReplyDraft",
                call=lambda helpdesk_service: helpdesk_service.generate_ticket_reply_draft(
                    ticket_public_id=UUID(request.ticket_public_id),
                    actor=request_context.actor,
                ),
            )
            if draft is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Заявка не найдена.")
            assert draft is not None
            return serialize_ticket_reply_draft(draft)

    async def PredictTicketCategory(
        self,
        request: helpdesk_pb2.PredictTicketCategoryRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketCategoryPrediction:
        async with self._rpc_scope(
            context,
            method="PredictTicketCategory",
            fallback_actor=self._request_actor(request),
        ) as request_context:
            prediction = await self._invoke_helpdesk(
                context,
                method="PredictTicketCategory",
                call=lambda helpdesk_service: helpdesk_service.predict_ticket_category(
                    deserialize_predict_ticket_category_command(request.command),
                    actor=request_context.actor,
                ),
            )
            return serialize_ticket_category_prediction(prediction)
