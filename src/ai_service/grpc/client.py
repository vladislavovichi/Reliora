# mypy: disable-error-code="attr-defined,name-defined"
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import grpc

from ai_service.grpc.auth import build_call_metadata
from ai_service.grpc.generated import ai_service_pb2, ai_service_pb2_grpc
from ai_service.grpc.translators import (
    deserialize_analyzed_ticket_sentiment_result,
    deserialize_generated_ticket_reply_draft_result,
    deserialize_generated_ticket_summary_result,
    deserialize_predicted_category_result,
    deserialize_suggested_macros_result,
    serialize_analyze_ticket_sentiment_command,
    serialize_generate_ticket_reply_draft_command,
    serialize_generate_ticket_summary_command,
    serialize_predict_category_command,
    serialize_suggest_macros_command,
)
from application.contracts.ai import (
    AIPredictedCategoryResult,
    AIPredictTicketCategoryCommand,
    AIServiceClient,
    AIServiceClientFactory,
    AnalyzedTicketSentimentResult,
    AnalyzeTicketSentimentCommand,
    GeneratedTicketReplyDraftResult,
    GeneratedTicketSummaryResult,
    GenerateTicketReplyDraftCommand,
    GenerateTicketSummaryCommand,
    SuggestedMacrosResult,
    SuggestMacrosCommand,
)
from application.errors import AIUnavailableError, ValidationAppError
from infrastructure.config.settings import AIServiceAuthConfig, AIServiceConfig, ResilienceConfig
from infrastructure.runtime_context import ensure_correlation_id

RETRYABLE_RPC_CODES = {
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
}
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GrpcAIServiceClient(AIServiceClient):
    stub: ai_service_pb2_grpc.HelpdeskAIServiceStub
    auth_config: AIServiceAuthConfig
    request_timeout_seconds: float
    read_retry_attempts: int
    retry_backoff_seconds: float

    async def get_service_status(self) -> tuple[str, str]:
        response = await self._invoke_unary(
            self.stub.GetAIServiceStatus,
            ai_service_pb2.Empty(),
            retryable=True,
        )
        return response.service, response.status

    async def generate_ticket_summary(
        self,
        command: GenerateTicketSummaryCommand,
    ) -> GeneratedTicketSummaryResult:
        response = await self._invoke_unary(
            self.stub.GenerateTicketSummary,
            serialize_generate_ticket_summary_command(command),
        )
        return deserialize_generated_ticket_summary_result(response)

    async def suggest_macros(
        self,
        command: SuggestMacrosCommand,
    ) -> SuggestedMacrosResult:
        response = await self._invoke_unary(
            self.stub.SuggestMacros,
            serialize_suggest_macros_command(command),
            retryable=True,
        )
        return deserialize_suggested_macros_result(response)

    async def generate_ticket_reply_draft(
        self,
        command: GenerateTicketReplyDraftCommand,
    ) -> GeneratedTicketReplyDraftResult:
        response = await self._invoke_unary(
            self.stub.GenerateTicketReplyDraft,
            serialize_generate_ticket_reply_draft_command(command),
        )
        return deserialize_generated_ticket_reply_draft_result(response)

    async def predict_ticket_category(
        self,
        command: AIPredictTicketCategoryCommand,
    ) -> AIPredictedCategoryResult:
        response = await self._invoke_unary(
            self.stub.PredictCategory,
            serialize_predict_category_command(command),
            retryable=True,
        )
        return deserialize_predicted_category_result(response)

    async def analyze_ticket_sentiment(
        self,
        command: AnalyzeTicketSentimentCommand,
    ) -> AnalyzedTicketSentimentResult:
        response = await self._invoke_unary(
            self.stub.AnalyzeTicketSentiment,
            serialize_analyze_ticket_sentiment_command(command),
            retryable=True,
        )
        return deserialize_analyzed_ticket_sentiment_result(response)

    async def _invoke_unary(
        self,
        call: Any,
        request: Any,
        *,
        retryable: bool = False,
    ) -> Any:
        attempts = self.read_retry_attempts if retryable else 1
        metadata = self._build_metadata()
        for attempt in range(1, attempts + 1):
            try:
                return await call(
                    request,
                    timeout=self.request_timeout_seconds,
                    metadata=metadata,
                )
            except grpc.aio.AioRpcError as exc:
                if not self._should_retry_rpc(exc, attempt=attempt, attempts=attempts):
                    raise _translate_rpc_error(exc) from exc
                await asyncio.sleep(self.retry_backoff_seconds * attempt)
        raise RuntimeError("unreachable")

    def _build_metadata(self) -> tuple[tuple[str, str], ...]:
        return build_call_metadata(
            auth_config=self.auth_config,
            correlation_id=ensure_correlation_id(),
        )

    def _should_retry_rpc(
        self,
        exc: grpc.aio.AioRpcError,
        *,
        attempt: int,
        attempts: int,
    ) -> bool:
        retryable = exc.code() in RETRYABLE_RPC_CODES and attempt < attempts
        if retryable:
            logger.warning(
                "AI gRPC transient read failure code=%s details=%s attempt=%s",
                exc.code().name,
                exc.details(),
                attempt,
            )
        return retryable


def build_ai_service_client_factory(
    config: AIServiceConfig,
    *,
    auth_config: AIServiceAuthConfig,
    resilience_config: ResilienceConfig,
) -> AIServiceClientFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[AIServiceClient]:
        channel = grpc.aio.insecure_channel(config.target)
        try:
            await asyncio.wait_for(
                channel.channel_ready(),
                timeout=resilience_config.grpc_connect_timeout_seconds,
            )
            yield GrpcAIServiceClient(
                stub=ai_service_pb2_grpc.HelpdeskAIServiceStub(channel),
                auth_config=auth_config,
                request_timeout_seconds=resilience_config.grpc_request_timeout_seconds,
                read_retry_attempts=max(resilience_config.grpc_read_retry_attempts, 1),
                retry_backoff_seconds=max(resilience_config.grpc_retry_backoff_seconds, 0.0),
            )
        finally:
            await channel.close()

    return provide


async def ping_ai_service(
    config: AIServiceConfig,
    *,
    auth_config: AIServiceAuthConfig,
    resilience_config: ResilienceConfig,
) -> bool:
    async with build_ai_service_client_factory(
        config,
        auth_config=auth_config,
        resilience_config=resilience_config,
    )() as client:
        service, status = await client.get_service_status()
    return service == "helpdesk-ai-service" and status == "ready"


def _translate_rpc_error(exc: grpc.aio.AioRpcError) -> Exception:
    if exc.code() == grpc.StatusCode.PERMISSION_DENIED:
        return PermissionError(exc.details() or "Внутренний запрос к ai-service отклонён.")
    if exc.code() == grpc.StatusCode.INVALID_ARGUMENT:
        return ValidationAppError(exc.details() or "Некорректный AI-запрос.")
    if exc.code() == grpc.StatusCode.UNAVAILABLE:
        return AIUnavailableError(exc.details() or "AI-service временно недоступен.")
    return RuntimeError(exc.details() or "Внутренняя ошибка ai-service.")
