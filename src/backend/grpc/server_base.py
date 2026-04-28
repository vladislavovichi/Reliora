from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any, TypeVar

import grpc

from application.contracts.actors import RequestActor
from application.errors import (
    AIUnavailableError,
    ApplicationError,
    BackendUnavailableError,
    ConcurrencyConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationAppError,
)
from application.services.authorization import AuthorizationError
from application.services.helpdesk.service import HelpdeskService, HelpdeskServiceFactory
from backend.grpc.auth import BackendRequestContext, resolve_backend_request_context
from backend.grpc.translators import deserialize_request_actor
from domain.tickets import InvalidTicketTransitionError
from infrastructure.config.settings import BackendAuthConfig
from infrastructure.runtime_context import bind_correlation_id, reset_correlation_id

logger = logging.getLogger(__name__)
_ServiceResultT = TypeVar("_ServiceResultT")
_ResponseT = TypeVar("_ResponseT")


class HelpdeskBackendGrpcServiceBase:
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
        except (PermissionError, ValueError) as exc:
            await abort_for_exception(context, exc, method=method)
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

    async def _invoke_helpdesk(
        self,
        context: grpc.aio.ServicerContext,
        *,
        method: str,
        call: Callable[[HelpdeskService], Awaitable[_ServiceResultT]],
    ) -> _ServiceResultT:
        try:
            async with self.helpdesk_service_factory() as helpdesk_service:
                return await call(helpdesk_service)
        except Exception as exc:
            await abort_for_exception(context, exc, method=method)
        raise RuntimeError("unreachable")

    async def _unary_rpc(
        self,
        context: grpc.aio.ServicerContext,
        *,
        method: str,
        call: Callable[
            [HelpdeskService, BackendRequestContext],
            Awaitable[_ServiceResultT],
        ],
        serialize: Callable[[_ServiceResultT], _ResponseT],
        fallback_actor: RequestActor | None = None,
    ) -> _ResponseT:
        async with self._rpc_scope(
            context,
            method=method,
            fallback_actor=fallback_actor,
        ) as request_context:
            result = await self._invoke_helpdesk(
                context,
                method=method,
                call=lambda helpdesk_service: call(helpdesk_service, request_context),
            )
            return serialize(result)

    async def _optional_unary_rpc(
        self,
        context: grpc.aio.ServicerContext,
        *,
        method: str,
        call: Callable[
            [HelpdeskService, BackendRequestContext],
            Awaitable[_ServiceResultT | None],
        ],
        serialize: Callable[[_ServiceResultT], _ResponseT],
        not_found_message: str,
        fallback_actor: RequestActor | None = None,
    ) -> _ResponseT:
        async with self._rpc_scope(
            context,
            method=method,
            fallback_actor=fallback_actor,
        ) as request_context:
            result = await self._invoke_helpdesk(
                context,
                method=method,
                call=lambda helpdesk_service: call(helpdesk_service, request_context),
            )
            if result is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, not_found_message)
            assert result is not None
            return serialize(result)

    async def _stream_rpc(
        self,
        context: grpc.aio.ServicerContext,
        *,
        method: str,
        call: Callable[
            [HelpdeskService, BackendRequestContext],
            Awaitable[Iterable[_ServiceResultT]],
        ],
        serialize: Callable[[_ServiceResultT], _ResponseT],
        fallback_actor: RequestActor | None = None,
    ) -> AsyncIterator[_ResponseT]:
        async with self._rpc_scope(
            context,
            method=method,
            fallback_actor=fallback_actor,
        ) as request_context:
            result = await self._invoke_helpdesk(
                context,
                method=method,
                call=lambda helpdesk_service: call(helpdesk_service, request_context),
            )
            for item in result:
                yield serialize(item)

    def _request_actor(self, request: Any) -> RequestActor | None:
        if hasattr(request, "HasField") and request.HasField("actor"):
            return deserialize_request_actor(request.actor)
        return None


async def abort_for_exception(
    context: grpc.aio.ServicerContext,
    exc: Exception,
    *,
    method: str,
) -> None:
    level = (
        logging.WARNING
        if isinstance(
            exc, (InvalidTicketTransitionError, AuthorizationError, PermissionError, ValueError)
        )
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
    if isinstance(exc, AuthorizationError):
        await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))
    if isinstance(exc, NotFoundError):
        await context.abort(grpc.StatusCode.NOT_FOUND, str(exc))
    if isinstance(exc, ForbiddenError):
        await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))
    if isinstance(exc, ValidationAppError):
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
    if isinstance(exc, RateLimitError):
        await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, str(exc))
    if isinstance(exc, (BackendUnavailableError, AIUnavailableError)):
        await context.abort(grpc.StatusCode.UNAVAILABLE, str(exc))
    if isinstance(exc, ConcurrencyConflictError):
        await context.abort(grpc.StatusCode.ABORTED, str(exc))
    if isinstance(exc, ApplicationError):
        await context.abort(grpc.StatusCode.UNKNOWN, str(exc))
    if isinstance(exc, PermissionError):
        await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))
    if isinstance(exc, ValueError):
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
    if isinstance(exc, (ConnectionError, OSError, TimeoutError)):
        await context.abort(grpc.StatusCode.UNAVAILABLE, "Backend сервис временно недоступен.")
    await context.abort(grpc.StatusCode.INTERNAL, "Внутренняя ошибка backend сервиса.")
