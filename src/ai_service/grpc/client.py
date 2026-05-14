# mypy: disable-error-code="attr-defined,name-defined"
import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import grpc
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt

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
    AIServiceStatus,
    AnalyzedTicketSentimentResult,
    AnalyzeTicketSentimentCommand,
    GeneratedTicketReplyDraftResult,
    GeneratedTicketSummaryResult,
    GenerateTicketReplyDraftCommand,
    GenerateTicketSummaryCommand,
    SuggestedMacrosResult,
    SuggestMacrosCommand,
)
from application.errors import AIUnavailableError, ForbiddenError, ValidationAppError
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

    async def get_service_status(self) -> AIServiceStatus:
        response = await self._invoke_unary(
            self.stub.GetAIServiceStatus,
            ai_service_pb2.Empty(),
            retryable=True,
        )
        return AIServiceStatus(
            service=response.service,
            status=response.status,
            provider=response.provider if response.HasField("provider") else None,
            model_id=response.model_id if response.HasField("model_id") else None,
            model_loaded=response.model_loaded,
            device=response.device if response.HasField("device") else None,
            dtype=response.dtype if response.HasField("dtype") else None,
            cache_dir=response.cache_dir if response.HasField("cache_dir") else None,
            max_concurrent_requests=(
                response.max_concurrent_requests if response.max_concurrent_requests > 0 else None
            ),
        )

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
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(_is_retryable_rpc_error),
                stop=stop_after_attempt(attempts),
                wait=lambda retry_state: self.retry_backoff_seconds * retry_state.attempt_number,
                sleep=self._sleep_before_retry,
                before_sleep=_log_ai_rpc_retry,
                reraise=True,
            ):
                with attempt:
                    return await call(
                        request,
                        timeout=self.request_timeout_seconds,
                        metadata=metadata,
                    )
        except grpc.aio.AioRpcError as exc:
            raise _translate_rpc_error(exc) from exc
        raise RuntimeError("unreachable")

    def _build_metadata(self) -> tuple[tuple[str, str], ...]:
        return build_call_metadata(
            auth_config=self.auth_config,
            correlation_id=ensure_correlation_id(),
        )

    async def _sleep_before_retry(self, delay: float) -> None:
        await asyncio.sleep(delay)


def _is_retryable_rpc_error(exc: BaseException) -> bool:
    return isinstance(exc, grpc.aio.AioRpcError) and exc.code() in RETRYABLE_RPC_CODES


def _log_ai_rpc_retry(retry_state: RetryCallState) -> None:
    if retry_state.outcome is None:
        return
    exc = retry_state.outcome.exception()
    if not isinstance(exc, grpc.aio.AioRpcError):
        return
    logger.warning(
        "AI gRPC transient read failure code=%s details=%s attempt=%s",
        exc.code().name,
        exc.details(),
        retry_state.attempt_number,
    )


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
        status = await client.get_service_status()
    return (
        status.service == "helpdesk-ai-service" and status.status == "ready" and status.model_loaded
    )


def _translate_rpc_error(exc: grpc.aio.AioRpcError) -> Exception:
    if exc.code() == grpc.StatusCode.PERMISSION_DENIED:
        return ForbiddenError(exc.details() or "Внутренний запрос к ai-service отклонён.")
    if exc.code() == grpc.StatusCode.INVALID_ARGUMENT:
        return ValidationAppError(exc.details() or "Некорректный AI-запрос.")
    if exc.code() in {grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED}:
        return AIUnavailableError(exc.details() or "AI-service временно недоступен.")
    return RuntimeError(exc.details() or "Внутренняя ошибка ai-service.")
