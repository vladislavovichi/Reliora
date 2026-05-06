# mypy: disable-error-code="attr-defined,name-defined"
from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import grpc

from backend.grpc.generated import helpdesk_pb2
from backend.grpc.server_base import HelpdeskBackendGrpcServiceBase
from backend.grpc.translators import (
    deserialize_apply_macro_command,
    deserialize_operator_identity,
    deserialize_predict_ticket_category_command,
    serialize_category,
    serialize_macro,
    serialize_macro_application_result,
    serialize_operator_invite_preview,
    serialize_operator_invite_redemption_result,
    serialize_operator_invite_summary,
    serialize_operator_role_mutation_result,
    serialize_operator_summary,
    serialize_tag,
    serialize_ticket_assist_snapshot,
    serialize_ticket_category_prediction,
    serialize_ticket_feedback,
    serialize_ticket_feedback_mutation_result,
    serialize_ticket_reply_draft,
    serialize_ticket_tag_mutation_result,
    serialize_ticket_tags,
)


class HelpdeskBackendOperationsGrpcMixin(HelpdeskBackendGrpcServiceBase):
    async def ListOperators(
        self,
        request: helpdesk_pb2.ListOperatorsRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[helpdesk_pb2.OperatorSummary]:
        async for operator in self._stream_rpc(
            context,
            method="ListOperators",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.list_operators(
                actor=request_context.actor
            ),
            serialize=serialize_operator_summary,
        ):
            yield operator

    async def CreateOperatorInvite(
        self,
        request: helpdesk_pb2.CreateOperatorInviteRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.OperatorInviteCodeSummary:
        return await self._unary_rpc(
            context,
            method="CreateOperatorInvite",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.create_operator_invite(
                actor=request_context.actor
            ),
            serialize=serialize_operator_invite_summary,
        )

    async def PreviewOperatorInvite(
        self,
        request: helpdesk_pb2.PreviewOperatorInviteRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.OperatorInviteCodePreview:
        return await self._unary_rpc(
            context,
            method="PreviewOperatorInvite",
            call=lambda helpdesk_service, _: helpdesk_service.preview_operator_invite(
                code=request.code
            ),
            serialize=serialize_operator_invite_preview,
        )

    async def RedeemOperatorInvite(
        self,
        request: helpdesk_pb2.RedeemOperatorInviteRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.OperatorInviteCodeRedemptionResult:
        return await self._unary_rpc(
            context,
            method="RedeemOperatorInvite",
            call=lambda helpdesk_service, _: helpdesk_service.redeem_operator_invite(
                code=request.code,
                operator=deserialize_operator_identity(request.operator),
            ),
            serialize=serialize_operator_invite_redemption_result,
        )

    async def PromoteOperator(
        self,
        request: helpdesk_pb2.PromoteOperatorRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.OperatorRoleMutationResult:
        return await self._unary_rpc(
            context,
            method="PromoteOperator",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.promote_operator(
                deserialize_operator_identity(request.operator),
                actor=request_context.actor,
            ),
            serialize=serialize_operator_role_mutation_result,
        )

    async def RevokeOperator(
        self,
        request: helpdesk_pb2.RevokeOperatorRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.OperatorRoleMutationResult:
        return await self._optional_unary_rpc(
            context,
            method="RevokeOperator",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.revoke_operator(
                telegram_user_id=request.telegram_user_id,
                actor=request_context.actor,
            ),
            serialize=serialize_operator_role_mutation_result,
            not_found_message="Оператор не найден.",
        )

    async def ListMacros(
        self,
        request: helpdesk_pb2.ListMacrosRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[helpdesk_pb2.MacroSummary]:
        async for macro in self._stream_rpc(
            context,
            method="ListMacros",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.list_macros(
                actor=request_context.actor
            ),
            serialize=serialize_macro,
        ):
            yield macro

    async def GetMacro(
        self,
        request: helpdesk_pb2.GetMacroRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.MacroSummary:
        return await self._optional_unary_rpc(
            context,
            method="GetMacro",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.get_macro(
                macro_id=request.macro_id,
                actor=request_context.actor,
            ),
            serialize=serialize_macro,
            not_found_message="Макрос не найден.",
        )

    async def CreateMacro(
        self,
        request: helpdesk_pb2.CreateMacroRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.MacroSummary:
        return await self._unary_rpc(
            context,
            method="CreateMacro",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.create_macro(
                title=request.title,
                body=request.body,
                actor=request_context.actor,
            ),
            serialize=serialize_macro,
        )

    async def UpdateMacroTitle(
        self,
        request: helpdesk_pb2.UpdateMacroTitleRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.MacroSummary:
        return await self._optional_unary_rpc(
            context,
            method="UpdateMacroTitle",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.update_macro_title(
                macro_id=request.macro_id,
                title=request.title,
                actor=request_context.actor,
            ),
            serialize=serialize_macro,
            not_found_message="Макрос не найден.",
        )

    async def UpdateMacroBody(
        self,
        request: helpdesk_pb2.UpdateMacroBodyRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.MacroSummary:
        return await self._optional_unary_rpc(
            context,
            method="UpdateMacroBody",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.update_macro_body(
                macro_id=request.macro_id,
                body=request.body,
                actor=request_context.actor,
            ),
            serialize=serialize_macro,
            not_found_message="Макрос не найден.",
        )

    async def DeleteMacro(
        self,
        request: helpdesk_pb2.DeleteMacroRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.MacroSummary:
        return await self._optional_unary_rpc(
            context,
            method="DeleteMacro",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.delete_macro(
                macro_id=request.macro_id,
                actor=request_context.actor,
            ),
            serialize=serialize_macro,
            not_found_message="Макрос не найден.",
        )

    async def ListTicketCategories(
        self,
        request: helpdesk_pb2.ListTicketCategoriesRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[helpdesk_pb2.TicketCategorySummary]:
        async for category in self._stream_rpc(
            context,
            method="ListTicketCategories",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.list_ticket_categories(
                actor=request_context.actor
            ),
            serialize=serialize_category,
        ):
            yield category

    async def GetTicketCategory(
        self,
        request: helpdesk_pb2.GetTicketCategoryRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketCategorySummary:
        return await self._optional_unary_rpc(
            context,
            method="GetTicketCategory",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.get_ticket_category(
                category_id=request.category_id,
                actor=request_context.actor,
            ),
            serialize=serialize_category,
            not_found_message="Категория не найдена.",
        )

    async def CreateTicketCategory(
        self,
        request: helpdesk_pb2.CreateTicketCategoryRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketCategorySummary:
        return await self._unary_rpc(
            context,
            method="CreateTicketCategory",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.create_ticket_category(
                title=request.title,
                actor=request_context.actor,
            ),
            serialize=serialize_category,
        )

    async def UpdateTicketCategoryTitle(
        self,
        request: helpdesk_pb2.UpdateTicketCategoryTitleRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketCategorySummary:
        return await self._optional_unary_rpc(
            context,
            method="UpdateTicketCategoryTitle",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: (
                helpdesk_service.update_ticket_category_title(
                    category_id=request.category_id,
                    title=request.title,
                    actor=request_context.actor,
                )
            ),
            serialize=serialize_category,
            not_found_message="Категория не найдена.",
        )

    async def SetTicketCategoryActive(
        self,
        request: helpdesk_pb2.SetTicketCategoryActiveRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketCategorySummary:
        return await self._optional_unary_rpc(
            context,
            method="SetTicketCategoryActive",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: (
                helpdesk_service.set_ticket_category_active(
                    category_id=request.category_id,
                    is_active=request.is_active,
                    actor=request_context.actor,
                )
            ),
            serialize=serialize_category,
            not_found_message="Категория не найдена.",
        )

    async def ListTicketTags(
        self,
        request: helpdesk_pb2.ListTicketTagsRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketTagsSummary:
        return await self._optional_unary_rpc(
            context,
            method="ListTicketTags",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.list_ticket_tags(
                ticket_public_id=UUID(request.ticket_public_id),
                actor=request_context.actor,
            ),
            serialize=serialize_ticket_tags,
            not_found_message="Заявка не найдена.",
        )

    async def ListAvailableTags(
        self,
        request: helpdesk_pb2.ListAvailableTagsRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[helpdesk_pb2.TagSummary]:
        async for tag in self._stream_rpc(
            context,
            method="ListAvailableTags",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.list_available_tags(
                actor=request_context.actor
            ),
            serialize=serialize_tag,
        ):
            yield tag

    async def AddTagToTicket(
        self,
        request: helpdesk_pb2.AddTagToTicketRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketTagMutationResult:
        return await self._optional_unary_rpc(
            context,
            method="AddTagToTicket",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.add_tag_to_ticket(
                ticket_public_id=UUID(request.ticket_public_id),
                tag_name=request.tag_name,
                actor=request_context.actor,
            ),
            serialize=serialize_ticket_tag_mutation_result,
            not_found_message="Заявка не найдена.",
        )

    async def RemoveTagFromTicket(
        self,
        request: helpdesk_pb2.RemoveTagFromTicketRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketTagMutationResult:
        return await self._optional_unary_rpc(
            context,
            method="RemoveTagFromTicket",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.remove_tag_from_ticket(
                ticket_public_id=UUID(request.ticket_public_id),
                tag_name=request.tag_name,
                actor=request_context.actor,
            ),
            serialize=serialize_ticket_tag_mutation_result,
            not_found_message="Заявка не найдена.",
        )

    async def SubmitTicketFeedbackRating(
        self,
        request: helpdesk_pb2.SubmitTicketFeedbackRatingRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketFeedbackMutationResult:
        return await self._unary_rpc(
            context,
            method="SubmitTicketFeedbackRating",
            call=lambda helpdesk_service, _: helpdesk_service.submit_ticket_feedback_rating(
                ticket_public_id=UUID(request.ticket_public_id),
                client_chat_id=request.client_chat_id,
                rating=request.rating,
            ),
            serialize=serialize_ticket_feedback_mutation_result,
        )

    async def GetTicketFeedback(
        self,
        request: helpdesk_pb2.GetTicketFeedbackRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketFeedbackSummary:
        return await self._optional_unary_rpc(
            context,
            method="GetTicketFeedback",
            call=lambda helpdesk_service, _: helpdesk_service.get_ticket_feedback(
                ticket_public_id=UUID(request.ticket_public_id),
            ),
            serialize=serialize_ticket_feedback,
            not_found_message="Оценка не найдена.",
        )

    async def AddTicketFeedbackComment(
        self,
        request: helpdesk_pb2.AddTicketFeedbackCommentRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketFeedbackMutationResult:
        return await self._unary_rpc(
            context,
            method="AddTicketFeedbackComment",
            call=lambda helpdesk_service, _: helpdesk_service.add_ticket_feedback_comment(
                ticket_public_id=UUID(request.ticket_public_id),
                client_chat_id=request.client_chat_id,
                comment=request.comment,
            ),
            serialize=serialize_ticket_feedback_mutation_result,
        )

    async def ApplyMacroToTicket(
        self,
        request: helpdesk_pb2.ApplyMacroToTicketRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.MacroApplicationResult:
        return await self._optional_unary_rpc(
            context,
            method="ApplyMacroToTicket",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.apply_macro_to_ticket(
                deserialize_apply_macro_command(request.command),
                actor=request_context.actor,
            ),
            serialize=serialize_macro_application_result,
            not_found_message="Заявка не найдена.",
        )

    async def GetTicketAssistSnapshot(
        self,
        request: helpdesk_pb2.GetTicketAssistSnapshotRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketAssistSnapshot:
        return await self._optional_unary_rpc(
            context,
            method="GetTicketAssistSnapshot",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: (
                helpdesk_service.get_ticket_ai_assist_snapshot(
                    ticket_public_id=UUID(request.ticket_public_id),
                    refresh_summary=request.refresh_summary,
                    actor=request_context.actor,
                )
            ),
            serialize=serialize_ticket_assist_snapshot,
            not_found_message="Заявка не найдена.",
        )

    async def GenerateTicketReplyDraft(
        self,
        request: helpdesk_pb2.GenerateTicketReplyDraftRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketReplyDraft:
        return await self._optional_unary_rpc(
            context,
            method="GenerateTicketReplyDraft",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: (
                helpdesk_service.generate_ticket_reply_draft(
                    ticket_public_id=UUID(request.ticket_public_id),
                    actor=request_context.actor,
                )
            ),
            serialize=serialize_ticket_reply_draft,
            not_found_message="Заявка не найдена.",
        )

    async def PredictTicketCategory(
        self,
        request: helpdesk_pb2.PredictTicketCategoryRequest,
        context: grpc.aio.ServicerContext,
    ) -> helpdesk_pb2.TicketCategoryPrediction:
        return await self._unary_rpc(
            context,
            method="PredictTicketCategory",
            fallback_actor=self._request_actor(request),
            call=lambda helpdesk_service, request_context: helpdesk_service.predict_ticket_category(
                deserialize_predict_ticket_category_command(request.command),
                actor=request_context.actor,
            ),
            serialize=serialize_ticket_category_prediction,
        )
