# mypy: disable-error-code="attr-defined,name-defined,no-untyped-def"
from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import TypeVar

import grpc

from ai_service.grpc.auth import AIServiceRequestContext, resolve_ai_service_request_context
from ai_service.grpc.generated import ai_service_pb2, ai_service_pb2_grpc
from ai_service.grpc.translators import (
    deserialize_generate_ticket_summary_command,
    deserialize_predict_category_command,
    deserialize_suggest_macros_command,
    serialize_generated_ticket_summary_result,
    serialize_predicted_category_result,
    serialize_suggested_macros_result,
)
from ai_service.service import AIApplicationService
from infrastructure.config.settings import AIServiceAuthConfig
from infrastructure.runtime_context import bind_correlation_id, reset_correlation_id

logger = logging.getLogger(__name__)
_ResponseT = TypeVar("_ResponseT")


@dataclass(slots=True)
class AIServiceGrpcService(ai_service_pb2_grpc.HelpdeskAIServiceServicer):
    service: AIApplicationService
    auth_config: AIServiceAuthConfig

    @asynccontextmanager
    async def _rpc_scope(
        self,
        context: grpc.aio.ServicerContext,
        *,
        method: str,
    ) -> AsyncIterator[AIServiceRequestContext]:
        try:
            request_context = resolve_ai_service_request_context(
                context,
                auth_config=self.auth_config,
            )
        except Exception as exc:
            await _abort_for_exception(context, exc, method=method)
            raise RuntimeError("unreachable") from exc
        correlation_token = bind_correlation_id(request_context.correlation_id)
        started_at = perf_counter()
        logger.info(
            "AI gRPC request started method=%s caller=%s peer=%s",
            method,
            request_context.caller,
            context.peer(),
        )
        try:
            yield request_context
            logger.info(
                "AI gRPC request completed method=%s caller=%s duration_ms=%s",
                method,
                request_context.caller,
                round((perf_counter() - started_at) * 1000, 2),
            )
        finally:
            reset_correlation_id(correlation_token)

    async def _invoke(
        self,
        context: grpc.aio.ServicerContext,
        *,
        method: str,
        call: Callable[[], Awaitable[_ResponseT]],
    ) -> _ResponseT:
        try:
            return await call()
        except Exception as exc:
            await _abort_for_exception(context, exc, method=method)
        raise RuntimeError("unreachable")

    async def GetAIServiceStatus(
        self,
        request: ai_service_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> ai_service_pb2.AIServiceStatus:
        del request
        async with self._rpc_scope(context, method="GetAIServiceStatus"):
            result = ai_service_pb2.AIServiceStatus(
                service="helpdesk-ai-service",
                status="ready",
                provider=self.service.config.normalized_provider,
            )
            if self.service.provider.model_id is not None:
                result.model_id = self.service.provider.model_id
            return result

    async def GenerateTicketSummary(
        self,
        request: ai_service_pb2.GenerateTicketSummaryCommand,
        context: grpc.aio.ServicerContext,
    ) -> ai_service_pb2.GenerateTicketSummaryResponse:
        async with self._rpc_scope(context, method="GenerateTicketSummary"):
            result = await self._invoke(
                context,
                method="GenerateTicketSummary",
                call=lambda: self.service.generate_ticket_summary(
                    deserialize_generate_ticket_summary_command(request)
                ),
            )
            return serialize_generated_ticket_summary_result(result)

    async def SuggestMacros(
        self,
        request: ai_service_pb2.SuggestMacrosCommand,
        context: grpc.aio.ServicerContext,
    ) -> ai_service_pb2.SuggestMacrosResponse:
        async with self._rpc_scope(context, method="SuggestMacros"):
            result = await self._invoke(
                context,
                method="SuggestMacros",
                call=lambda: self.service.suggest_macros(
                    deserialize_suggest_macros_command(request)
                ),
            )
            return serialize_suggested_macros_result(result)

    async def PredictCategory(
        self,
        request: ai_service_pb2.PredictCategoryCommand,
        context: grpc.aio.ServicerContext,
    ) -> ai_service_pb2.PredictCategoryResponse:
        async with self._rpc_scope(context, method="PredictCategory"):
            result = await self._invoke(
                context,
                method="PredictCategory",
                call=lambda: self.service.predict_ticket_category(
                    deserialize_predict_category_command(request)
                ),
            )
            return serialize_predicted_category_result(result)


@dataclass(slots=True)
class AIServiceGrpcServer:
    service: AIApplicationService
    bind_target: str
    auth_config: AIServiceAuthConfig
    server: grpc.aio.Server = field(init=False)
    bound_port: int = field(init=False)

    def __post_init__(self) -> None:
        self.server = grpc.aio.server()
        ai_service_pb2_grpc.add_HelpdeskAIServiceServicer_to_server(
            AIServiceGrpcService(
                service=self.service,
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


def build_ai_service_grpc_server(
    *,
    service: AIApplicationService,
    bind_target: str,
    auth_config: AIServiceAuthConfig,
) -> AIServiceGrpcServer:
    return AIServiceGrpcServer(
        service=service,
        bind_target=bind_target,
        auth_config=auth_config,
    )


async def _abort_for_exception(
    context: grpc.aio.ServicerContext,
    exc: Exception,
    *,
    method: str,
) -> None:
    level = logging.WARNING if isinstance(exc, (PermissionError, ValueError)) else logging.ERROR
    logger.log(
        level,
        "AI gRPC request failed method=%s error_type=%s error=%s",
        method,
        exc.__class__.__name__,
        exc,
        exc_info=level >= logging.ERROR,
    )
    if isinstance(exc, PermissionError):
        await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))
    if isinstance(exc, ValueError):
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
    await context.abort(grpc.StatusCode.INTERNAL, "Внутренняя ошибка ai-service.")
