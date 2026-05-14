# mypy: disable-error-code="attr-defined,name-defined"
import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, TypeVar
from uuid import UUID

import grpc
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt

from application.ai.summaries import (
    TicketAssistSnapshot,
    TicketCategoryPrediction,
    TicketReplyDraft,
)
from application.contracts.actors import OperatorIdentity, RequestActor
from application.contracts.ai import PredictTicketCategoryCommand
from application.contracts.tickets import (
    AddInternalNoteCommand,
    ApplyMacroToTicketCommand,
    AssignNextQueuedTicketCommand,
    ClientTicketMessageCommand,
    OperatorTicketReplyCommand,
    TicketAssignmentCommand,
)
from application.errors import (
    BackendUnavailableError,
    ConcurrencyConflictError,
    ForbiddenError,
    InternalApplicationError,
    NotFoundError,
    RateLimitError,
    ValidationAppError,
)
from application.services.stats import AnalyticsWindow, HelpdeskAnalyticsSnapshot
from application.use_cases.analytics.exports import (
    AnalyticsExportFormat,
    AnalyticsSection,
    AnalyticsSnapshotExport,
)
from application.use_cases.tickets.exports import TicketReportExport, TicketReportFormat
from application.use_cases.tickets.operator_invites import (
    OperatorInviteCodePreview,
    OperatorInviteCodeRedemptionResult,
    OperatorInviteCodeSummary,
)
from application.use_cases.tickets.summaries import (
    AccessContextSummary,
    HistoricalTicketSummary,
    MacroApplicationResult,
    MacroSummary,
    OperatorReplyResult,
    OperatorRoleMutationResult,
    OperatorSummary,
    OperatorTicketSummary,
    QueuedTicketSummary,
    TagSummary,
    TicketCategorySummary,
    TicketDetailsSummary,
    TicketFeedbackMutationResult,
    TicketFeedbackSummary,
    TicketSummary,
    TicketTagMutationResult,
    TicketTagsSummary,
)
from backend.grpc.auth import build_call_metadata
from backend.grpc.contracts import HelpdeskBackendClient, HelpdeskBackendClientFactory
from backend.grpc.generated import helpdesk_pb2, helpdesk_pb2_grpc
from backend.grpc.translators import (
    deserialize_access_context,
    deserialize_analytics_export,
    deserialize_analytics_snapshot,
    deserialize_archived_ticket,
    deserialize_category,
    deserialize_export,
    deserialize_macro,
    deserialize_macro_application_result,
    deserialize_operator_invite_preview,
    deserialize_operator_invite_redemption_result,
    deserialize_operator_invite_summary,
    deserialize_operator_reply_result,
    deserialize_operator_role_mutation_result,
    deserialize_operator_summary,
    deserialize_operator_ticket,
    deserialize_queued_ticket,
    deserialize_tag,
    deserialize_ticket_assist_snapshot,
    deserialize_ticket_category_prediction,
    deserialize_ticket_details,
    deserialize_ticket_feedback,
    deserialize_ticket_feedback_mutation_result,
    deserialize_ticket_reply_draft,
    deserialize_ticket_summary,
    deserialize_ticket_tag_mutation_result,
    deserialize_ticket_tags,
    serialize_add_internal_note_command,
    serialize_apply_macro_command,
    serialize_assign_next_command,
    serialize_client_ticket_message_command,
    serialize_operator_identity,
    serialize_operator_reply_command,
    serialize_predict_ticket_category_command,
    serialize_request_actor,
    serialize_ticket_assignment_command,
)
from domain.tickets import InvalidTicketTransitionError
from infrastructure.config.settings import BackendAuthConfig, BackendServiceConfig, ResilienceConfig
from infrastructure.runtime_context import ensure_correlation_id

RETRYABLE_RPC_CODES = {
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
}
_RPC_ERROR_MAP: dict[grpc.StatusCode, tuple[type[Exception], str]] = {
    grpc.StatusCode.NOT_FOUND: (NotFoundError, "Ресурс не найден."),
    grpc.StatusCode.FAILED_PRECONDITION: (
        InvalidTicketTransitionError,
        "Недопустимый переход заявки.",
    ),
    grpc.StatusCode.PERMISSION_DENIED: (ForbiddenError, "Недостаточно прав."),
    grpc.StatusCode.INVALID_ARGUMENT: (ValidationAppError, "Некорректный запрос."),
    grpc.StatusCode.RESOURCE_EXHAUSTED: (RateLimitError, "Слишком много запросов."),
    grpc.StatusCode.UNAVAILABLE: (
        BackendUnavailableError,
        "Backend сервис временно недоступен.",
    ),
    grpc.StatusCode.ABORTED: (
        ConcurrencyConflictError,
        "Операция конфликтует с другим изменением.",
    ),
}
logger = logging.getLogger(__name__)
ResultT = TypeVar("ResultT")


@dataclass(slots=True)
class GrpcHelpdeskBackendClient(HelpdeskBackendClient):
    stub: helpdesk_pb2_grpc.HelpdeskBackendServiceStub
    auth_config: BackendAuthConfig
    request_timeout_seconds: float
    read_retry_attempts: int
    retry_backoff_seconds: float

    async def get_backend_status(self) -> tuple[str, str]:
        response = await self._call_unary_raw(
            self.stub.GetBackendStatus,
            helpdesk_pb2.Empty(),
            retryable=True,
        )
        return response.service, response.status

    async def get_access_context(
        self,
        *,
        actor: RequestActor,
    ) -> AccessContextSummary:
        request = helpdesk_pb2.GetAccessContextRequest()
        _apply_actor(request, actor)
        return await self._call_unary_required(
            self.stub.GetAccessContext,
            request,
            actor=actor,
            retryable=True,
            deserialize=deserialize_access_context,
        )

    async def get_client_active_ticket(self, *, client_chat_id: int) -> TicketSummary | None:
        return await self._call_unary_optional(
            self.stub.GetClientActiveTicket,
            helpdesk_pb2.GetClientActiveTicketRequest(client_chat_id=client_chat_id),
            retryable=True,
            deserialize=deserialize_ticket_summary,
        )

    async def list_client_ticket_categories(self) -> tuple[TicketCategorySummary, ...]:
        response = await self._collect_stream(
            lambda metadata: self.stub.ListClientTicketCategories(
                helpdesk_pb2.Empty(),
                timeout=self.request_timeout_seconds,
                metadata=metadata,
            ),
            retryable=True,
        )
        return tuple(deserialize_category(item) for item in response)

    async def create_ticket_from_client_message(
        self,
        command: ClientTicketMessageCommand,
    ) -> TicketSummary:
        request = helpdesk_pb2.CreateTicketFromClientMessageRequest()
        request.command.CopyFrom(serialize_client_ticket_message_command(command))
        return await self._call_unary_required(
            self.stub.CreateTicketFromClientMessage,
            request,
            deserialize=deserialize_ticket_summary,
        )

    async def create_ticket_from_client_intake(
        self,
        command: ClientTicketMessageCommand,
    ) -> TicketSummary:
        request = helpdesk_pb2.CreateTicketFromClientIntakeRequest()
        request.command.CopyFrom(serialize_client_ticket_message_command(command))
        return await self._call_unary_required(
            self.stub.CreateTicketFromClientIntake,
            request,
            deserialize=deserialize_ticket_summary,
        )

    async def get_ticket_details(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketDetailsSummary | None:
        request = helpdesk_pb2.GetTicketDetailsRequest(ticket_public_id=str(ticket_public_id))
        _apply_actor(request, actor)
        return await self._call_unary_optional(
            self.stub.GetTicketDetails,
            request,
            actor=actor,
            retryable=True,
            deserialize=deserialize_ticket_details,
        )

    async def list_queued_tickets(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> tuple[QueuedTicketSummary, ...]:
        request = helpdesk_pb2.ListQueuedTicketsRequest()
        _apply_actor(request, actor)
        response = await self._collect_stream(
            lambda metadata: self.stub.ListQueuedTickets(
                request,
                timeout=self.request_timeout_seconds,
                metadata=metadata,
            ),
            actor=actor,
            retryable=True,
        )
        return tuple(deserialize_queued_ticket(item) for item in response)

    async def list_operator_tickets(
        self,
        *,
        operator_telegram_user_id: int,
        actor: RequestActor | None = None,
    ) -> tuple[OperatorTicketSummary, ...]:
        request = helpdesk_pb2.ListOperatorTicketsRequest(
            operator_telegram_user_id=operator_telegram_user_id
        )
        _apply_actor(request, actor)
        response = await self._collect_stream(
            lambda metadata: self.stub.ListOperatorTickets(
                request,
                timeout=self.request_timeout_seconds,
                metadata=metadata,
            ),
            actor=actor,
            retryable=True,
        )
        return tuple(deserialize_operator_ticket(item) for item in response)

    async def list_archived_tickets(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> tuple[HistoricalTicketSummary, ...]:
        request = helpdesk_pb2.ListArchivedTicketsRequest()
        _apply_actor(request, actor)
        response = await self._collect_stream(
            lambda metadata: self.stub.ListArchivedTickets(
                request,
                timeout=self.request_timeout_seconds,
                metadata=metadata,
            ),
            actor=actor,
            retryable=True,
        )
        return tuple(deserialize_archived_ticket(item) for item in response)

    async def assign_next_ticket_to_operator(
        self,
        command: AssignNextQueuedTicketCommand,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        request = helpdesk_pb2.AssignNextQueuedTicketRequest()
        request.command.CopyFrom(serialize_assign_next_command(command))
        _apply_actor(request, actor)
        return await self._call_unary_optional(
            self.stub.AssignNextQueuedTicket,
            request,
            actor=actor,
            deserialize=deserialize_ticket_summary,
        )

    async def assign_ticket_to_operator(
        self,
        command: TicketAssignmentCommand,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        request = helpdesk_pb2.AssignTicketToOperatorRequest()
        request.command.CopyFrom(serialize_ticket_assignment_command(command))
        _apply_actor(request, actor)
        return await self._call_unary_optional(
            self.stub.AssignTicketToOperator,
            request,
            actor=actor,
            deserialize=deserialize_ticket_summary,
        )

    async def close_ticket(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        return await self._call_unary_optional(
            self.stub.CloseTicket,
            helpdesk_pb2.CloseTicketRequest(ticket_public_id=str(ticket_public_id)),
            actor=actor,
            deserialize=deserialize_ticket_summary,
        )

    async def close_ticket_as_operator(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None,
    ) -> TicketSummary | None:
        request = helpdesk_pb2.CloseTicketAsOperatorRequest(ticket_public_id=str(ticket_public_id))
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.CloseTicketAsOperator,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_ticket_summary(result)

    async def escalate_ticket_as_operator(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None,
    ) -> TicketSummary | None:
        request = helpdesk_pb2.EscalateTicketAsOperatorRequest(
            ticket_public_id=str(ticket_public_id)
        )
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.EscalateTicketAsOperator,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_ticket_summary(result)

    async def reply_to_ticket_as_operator(
        self,
        command: OperatorTicketReplyCommand,
        actor: RequestActor | None = None,
    ) -> OperatorReplyResult | None:
        request = helpdesk_pb2.ReplyToTicketAsOperatorRequest()
        request.command.CopyFrom(serialize_operator_reply_command(command))
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.ReplyToTicketAsOperator,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_operator_reply_result(result)

    async def add_internal_note_to_ticket(
        self,
        command: AddInternalNoteCommand,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        request = helpdesk_pb2.AddInternalNoteToTicketRequest()
        request.command.CopyFrom(serialize_add_internal_note_command(command))
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.AddInternalNoteToTicket,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_ticket_summary(result)

    async def list_operators(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> tuple[OperatorSummary, ...]:
        request = helpdesk_pb2.ListOperatorsRequest()
        _apply_actor(request, actor)
        response = await self._collect_stream(
            lambda metadata: self.stub.ListOperators(
                request,
                timeout=self.request_timeout_seconds,
                metadata=metadata,
            ),
            actor=actor,
            retryable=True,
        )
        return tuple(deserialize_operator_summary(item) for item in response)

    async def create_operator_invite(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> OperatorInviteCodeSummary:
        request = helpdesk_pb2.CreateOperatorInviteRequest()
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.CreateOperatorInvite,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            raise _translate_rpc_error(exc) from exc
        return deserialize_operator_invite_summary(result)

    async def preview_operator_invite(
        self,
        *,
        code: str,
    ) -> OperatorInviteCodePreview:
        try:
            result = await self._invoke_unary(
                self.stub.PreviewOperatorInvite,
                helpdesk_pb2.PreviewOperatorInviteRequest(code=code),
            )
        except grpc.aio.AioRpcError as exc:
            raise _translate_rpc_error(exc) from exc
        return deserialize_operator_invite_preview(result)

    async def redeem_operator_invite(
        self,
        *,
        code: str,
        operator: OperatorIdentity,
    ) -> OperatorInviteCodeRedemptionResult:
        request = helpdesk_pb2.RedeemOperatorInviteRequest(code=code)
        request.operator.CopyFrom(serialize_operator_identity(operator))
        try:
            result = await self._invoke_unary(
                self.stub.RedeemOperatorInvite,
                request,
            )
        except grpc.aio.AioRpcError as exc:
            raise _translate_rpc_error(exc) from exc
        return deserialize_operator_invite_redemption_result(result)

    async def promote_operator(
        self,
        operator: OperatorIdentity,
        actor: RequestActor | None = None,
    ) -> OperatorRoleMutationResult:
        request = helpdesk_pb2.PromoteOperatorRequest()
        request.operator.CopyFrom(serialize_operator_identity(operator))
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.PromoteOperator,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            raise _translate_rpc_error(exc) from exc
        return deserialize_operator_role_mutation_result(result)

    async def revoke_operator(
        self,
        *,
        telegram_user_id: int,
        actor: RequestActor | None = None,
    ) -> OperatorRoleMutationResult | None:
        request = helpdesk_pb2.RevokeOperatorRequest(telegram_user_id=telegram_user_id)
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.RevokeOperator,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_operator_role_mutation_result(result)

    async def list_macros(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> tuple[MacroSummary, ...]:
        request = helpdesk_pb2.ListMacrosRequest()
        _apply_actor(request, actor)
        response = await self._collect_stream(
            lambda metadata: self.stub.ListMacros(
                request,
                timeout=self.request_timeout_seconds,
                metadata=metadata,
            ),
            actor=actor,
            retryable=True,
        )
        return tuple(deserialize_macro(item) for item in response)

    async def get_macro(
        self,
        *,
        macro_id: int,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        request = helpdesk_pb2.GetMacroRequest(macro_id=macro_id)
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(self.stub.GetMacro, request, actor=actor)
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_macro(result)

    async def create_macro(
        self,
        *,
        title: str,
        body: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary:
        request = helpdesk_pb2.CreateMacroRequest(title=title, body=body)
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(self.stub.CreateMacro, request, actor=actor)
        except grpc.aio.AioRpcError as exc:
            raise _translate_rpc_error(exc) from exc
        return deserialize_macro(result)

    async def update_macro_title(
        self,
        *,
        macro_id: int,
        title: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        request = helpdesk_pb2.UpdateMacroTitleRequest(macro_id=macro_id, title=title)
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(self.stub.UpdateMacroTitle, request, actor=actor)
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_macro(result)

    async def update_macro_body(
        self,
        *,
        macro_id: int,
        body: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        request = helpdesk_pb2.UpdateMacroBodyRequest(macro_id=macro_id, body=body)
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(self.stub.UpdateMacroBody, request, actor=actor)
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_macro(result)

    async def delete_macro(
        self,
        *,
        macro_id: int,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        request = helpdesk_pb2.DeleteMacroRequest(macro_id=macro_id)
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(self.stub.DeleteMacro, request, actor=actor)
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_macro(result)

    async def list_ticket_categories(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> tuple[TicketCategorySummary, ...]:
        request = helpdesk_pb2.ListTicketCategoriesRequest()
        _apply_actor(request, actor)
        response = await self._collect_stream(
            lambda metadata: self.stub.ListTicketCategories(
                request,
                timeout=self.request_timeout_seconds,
                metadata=metadata,
            ),
            actor=actor,
            retryable=True,
        )
        return tuple(deserialize_category(item) for item in response)

    async def get_ticket_category(
        self,
        *,
        category_id: int,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None:
        request = helpdesk_pb2.GetTicketCategoryRequest(category_id=category_id)
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.GetTicketCategory,
                request,
                actor=actor,
                retryable=True,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_category(result)

    async def create_ticket_category(
        self,
        *,
        title: str,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary:
        request = helpdesk_pb2.CreateTicketCategoryRequest(title=title)
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.CreateTicketCategory,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            raise _translate_rpc_error(exc) from exc
        return deserialize_category(result)

    async def update_ticket_category_title(
        self,
        *,
        category_id: int,
        title: str,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None:
        request = helpdesk_pb2.UpdateTicketCategoryTitleRequest(
            category_id=category_id,
            title=title,
        )
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.UpdateTicketCategoryTitle,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_category(result)

    async def set_ticket_category_active(
        self,
        *,
        category_id: int,
        is_active: bool,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None:
        request = helpdesk_pb2.SetTicketCategoryActiveRequest(
            category_id=category_id,
            is_active=is_active,
        )
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.SetTicketCategoryActive,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_category(result)

    async def list_ticket_tags(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketTagsSummary | None:
        request = helpdesk_pb2.ListTicketTagsRequest(ticket_public_id=str(ticket_public_id))
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.ListTicketTags,
                request,
                actor=actor,
                retryable=True,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_ticket_tags(result)

    async def list_available_tags(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> tuple[TagSummary, ...]:
        request = helpdesk_pb2.ListAvailableTagsRequest()
        _apply_actor(request, actor)
        response = await self._collect_stream(
            lambda metadata: self.stub.ListAvailableTags(
                request,
                timeout=self.request_timeout_seconds,
                metadata=metadata,
            ),
            actor=actor,
            retryable=True,
        )
        return tuple(deserialize_tag(item) for item in response)

    async def add_tag_to_ticket(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
        actor: RequestActor | None = None,
    ) -> TicketTagMutationResult | None:
        request = helpdesk_pb2.AddTagToTicketRequest(
            ticket_public_id=str(ticket_public_id),
            tag_name=tag_name,
        )
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(self.stub.AddTagToTicket, request, actor=actor)
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_ticket_tag_mutation_result(result)

    async def remove_tag_from_ticket(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
        actor: RequestActor | None = None,
    ) -> TicketTagMutationResult | None:
        request = helpdesk_pb2.RemoveTagFromTicketRequest(
            ticket_public_id=str(ticket_public_id),
            tag_name=tag_name,
        )
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.RemoveTagFromTicket,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_ticket_tag_mutation_result(result)

    async def submit_ticket_feedback_rating(
        self,
        *,
        ticket_public_id: UUID,
        client_chat_id: int,
        rating: int,
    ) -> TicketFeedbackMutationResult:
        request = helpdesk_pb2.SubmitTicketFeedbackRatingRequest(
            ticket_public_id=str(ticket_public_id),
            client_chat_id=client_chat_id,
            rating=rating,
        )
        try:
            result = await self._invoke_unary(self.stub.SubmitTicketFeedbackRating, request)
        except grpc.aio.AioRpcError as exc:
            raise _translate_rpc_error(exc) from exc
        return deserialize_ticket_feedback_mutation_result(result)

    async def get_ticket_feedback(
        self,
        *,
        ticket_public_id: UUID,
    ) -> TicketFeedbackSummary | None:
        try:
            result = await self._invoke_unary(
                self.stub.GetTicketFeedback,
                helpdesk_pb2.GetTicketFeedbackRequest(ticket_public_id=str(ticket_public_id)),
                retryable=True,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_ticket_feedback(result)

    async def add_ticket_feedback_comment(
        self,
        *,
        ticket_public_id: UUID,
        client_chat_id: int,
        comment: str,
    ) -> TicketFeedbackMutationResult:
        request = helpdesk_pb2.AddTicketFeedbackCommentRequest(
            ticket_public_id=str(ticket_public_id),
            client_chat_id=client_chat_id,
            comment=comment,
        )
        try:
            result = await self._invoke_unary(self.stub.AddTicketFeedbackComment, request)
        except grpc.aio.AioRpcError as exc:
            raise _translate_rpc_error(exc) from exc
        return deserialize_ticket_feedback_mutation_result(result)

    async def apply_macro_to_ticket(
        self,
        command: ApplyMacroToTicketCommand,
        actor: RequestActor | None = None,
    ) -> MacroApplicationResult | None:
        request = helpdesk_pb2.ApplyMacroToTicketRequest()
        request.command.CopyFrom(serialize_apply_macro_command(command))
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.ApplyMacroToTicket,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_macro_application_result(result)

    async def get_ticket_ai_assist_snapshot(
        self,
        *,
        ticket_public_id: UUID,
        refresh_summary: bool = False,
        actor: RequestActor | None = None,
    ) -> TicketAssistSnapshot | None:
        request = helpdesk_pb2.GetTicketAssistSnapshotRequest(
            ticket_public_id=str(ticket_public_id),
            refresh_summary=refresh_summary,
        )
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.GetTicketAssistSnapshot,
                request,
                actor=actor,
                retryable=True,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_ticket_assist_snapshot(result)

    async def generate_ticket_reply_draft(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketReplyDraft | None:
        request = helpdesk_pb2.GenerateTicketReplyDraftRequest(
            ticket_public_id=str(ticket_public_id),
        )
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.GenerateTicketReplyDraft,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_ticket_reply_draft(result)

    async def predict_ticket_category(
        self,
        command: PredictTicketCategoryCommand,
        *,
        actor: RequestActor | None = None,
    ) -> TicketCategoryPrediction:
        request = helpdesk_pb2.PredictTicketCategoryRequest()
        request.command.CopyFrom(serialize_predict_ticket_category_command(command))
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.PredictTicketCategory,
                request,
                actor=actor,
                retryable=True,
            )
        except grpc.aio.AioRpcError as exc:
            raise _translate_rpc_error(exc) from exc
        return deserialize_ticket_category_prediction(result)

    async def export_ticket_report(
        self,
        *,
        ticket_public_id: UUID,
        format: TicketReportFormat,
        actor: RequestActor | None = None,
    ) -> TicketReportExport | None:
        request = helpdesk_pb2.ExportTicketReportRequest(
            ticket_public_id=str(ticket_public_id),
            format=format.value,
        )
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.ExportTicketReport,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize_export(result)

    async def get_analytics_snapshot(
        self,
        *,
        window: AnalyticsWindow,
        actor: RequestActor | None = None,
    ) -> HelpdeskAnalyticsSnapshot:
        request = helpdesk_pb2.GetAnalyticsSnapshotRequest(window=window.value)
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.GetAnalyticsSnapshot,
                request,
                actor=actor,
                retryable=True,
            )
        except grpc.aio.AioRpcError as exc:
            raise _translate_rpc_error(exc) from exc
        return deserialize_analytics_snapshot(result)

    async def export_analytics_snapshot(
        self,
        *,
        window: AnalyticsWindow,
        section: AnalyticsSection,
        format: AnalyticsExportFormat,
        actor: RequestActor | None = None,
    ) -> AnalyticsSnapshotExport:
        request = helpdesk_pb2.ExportAnalyticsSnapshotRequest(
            window=window.value,
            section=section.value,
            format=format.value,
        )
        _apply_actor(request, actor)
        try:
            result = await self._invoke_unary(
                self.stub.ExportAnalyticsSnapshot,
                request,
                actor=actor,
            )
        except grpc.aio.AioRpcError as exc:
            raise _translate_rpc_error(exc) from exc
        return deserialize_analytics_export(result)

    async def _invoke_unary(
        self,
        call: Any,
        request: Any,
        *,
        actor: RequestActor | None = None,
        retryable: bool = False,
    ) -> Any:
        attempts = self.read_retry_attempts if retryable else 1
        metadata = self._build_metadata(actor=actor)
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_is_retryable_rpc_error),
            stop=stop_after_attempt(attempts),
            wait=lambda retry_state: self.retry_backoff_seconds * retry_state.attempt_number,
            sleep=self._sleep_before_retry,
            before_sleep=_log_backend_rpc_retry,
            reraise=True,
        ):
            with attempt:
                return await call(
                    request,
                    timeout=self.request_timeout_seconds,
                    metadata=metadata,
                )

        raise RuntimeError("unreachable")

    async def _call_unary_raw(
        self,
        call: Any,
        request: Any,
        *,
        actor: RequestActor | None = None,
        retryable: bool = False,
    ) -> Any:
        try:
            return await self._invoke_unary(
                call,
                request,
                actor=actor,
                retryable=retryable,
            )
        except grpc.aio.AioRpcError as exc:
            raise _translate_rpc_error(exc) from exc

    async def _call_unary_required(
        self,
        call: Any,
        request: Any,
        *,
        actor: RequestActor | None = None,
        retryable: bool = False,
        deserialize: Callable[[Any], ResultT],
    ) -> ResultT:
        result = await self._call_unary_raw(
            call,
            request,
            actor=actor,
            retryable=retryable,
        )
        return deserialize(result)

    async def _call_unary_optional(
        self,
        call: Any,
        request: Any,
        *,
        actor: RequestActor | None = None,
        retryable: bool = False,
        deserialize: Callable[[Any], ResultT],
    ) -> ResultT | None:
        try:
            result = await self._invoke_unary(
                call,
                request,
                actor=actor,
                retryable=retryable,
            )
        except grpc.aio.AioRpcError as exc:
            _raise_optional_rpc_error(exc)
            return None
        return deserialize(result)

    async def _collect_stream(
        self,
        call_factory: Any,
        *,
        actor: RequestActor | None = None,
        retryable: bool = False,
    ) -> list[object]:
        attempts = self.read_retry_attempts if retryable else 1
        metadata = self._build_metadata(actor=actor)
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(_is_retryable_rpc_error),
                stop=stop_after_attempt(attempts),
                wait=lambda retry_state: self.retry_backoff_seconds * retry_state.attempt_number,
                sleep=self._sleep_before_retry,
                before_sleep=_log_backend_rpc_retry,
                reraise=True,
            ):
                with attempt:
                    call = call_factory(metadata)
                    items: list[object] = []
                    async for item in call:
                        items.append(item)
                    return items
        except grpc.aio.AioRpcError as exc:
            raise _translate_rpc_error(exc) from exc

        raise RuntimeError("unreachable")

    def _build_metadata(self, *, actor: RequestActor | None) -> tuple[tuple[str, str], ...]:
        return build_call_metadata(
            auth_config=self.auth_config,
            correlation_id=ensure_correlation_id(),
            actor=actor,
        )

    async def _sleep_before_retry(self, delay: float) -> None:
        await asyncio.sleep(delay)


def _is_retryable_rpc_error(exc: BaseException) -> bool:
    return isinstance(exc, grpc.aio.AioRpcError) and exc.code() in RETRYABLE_RPC_CODES


def _log_backend_rpc_retry(retry_state: RetryCallState) -> None:
    if retry_state.outcome is None:
        return
    exc = retry_state.outcome.exception()
    if not isinstance(exc, grpc.aio.AioRpcError):
        return
    logger.warning(
        "gRPC transient read failure code=%s details=%s attempt=%s",
        exc.code().name,
        exc.details(),
        retry_state.attempt_number,
    )


def build_helpdesk_backend_client_factory(
    config: BackendServiceConfig,
    *,
    auth_config: BackendAuthConfig,
    resilience_config: ResilienceConfig,
) -> HelpdeskBackendClientFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[HelpdeskBackendClient]:
        channel = grpc.aio.insecure_channel(config.target)
        try:
            await asyncio.wait_for(
                channel.channel_ready(),
                timeout=resilience_config.grpc_connect_timeout_seconds,
            )
            yield GrpcHelpdeskBackendClient(
                stub=helpdesk_pb2_grpc.HelpdeskBackendServiceStub(channel),
                auth_config=auth_config,
                request_timeout_seconds=resilience_config.grpc_request_timeout_seconds,
                read_retry_attempts=max(resilience_config.grpc_read_retry_attempts, 1),
                retry_backoff_seconds=max(resilience_config.grpc_retry_backoff_seconds, 0.0),
            )
        finally:
            await channel.close()

    return provide


async def ping_helpdesk_backend(
    config: BackendServiceConfig,
    *,
    auth_config: BackendAuthConfig,
    resilience_config: ResilienceConfig,
) -> bool:
    async with build_helpdesk_backend_client_factory(
        config,
        auth_config=auth_config,
        resilience_config=resilience_config,
    )() as client:
        service, status = await client.get_backend_status()
    return service == "helpdesk-backend" and status == "ready"


def _apply_actor(message: Any, actor: RequestActor | None) -> None:
    if actor is None:
        return
    message.actor.CopyFrom(serialize_request_actor(actor))


def _raise_optional_rpc_error(exc: grpc.aio.AioRpcError) -> None:
    if exc.code() == grpc.StatusCode.NOT_FOUND:
        return
    raise _translate_rpc_error(exc) from exc


def _translate_rpc_error(exc: grpc.aio.AioRpcError) -> Exception:
    details = exc.details() or ""
    mapped = _RPC_ERROR_MAP.get(exc.code())
    if mapped is not None:
        error_cls, fallback_message = mapped
        return error_cls(details or fallback_message)
    return InternalApplicationError(details or "Внутренняя ошибка backend gRPC.")
