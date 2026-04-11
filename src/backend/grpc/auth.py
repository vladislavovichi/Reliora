from __future__ import annotations

from dataclasses import dataclass

import grpc

from application.contracts.actors import RequestActor
from infrastructure.config.settings import BackendAuthConfig

INTERNAL_AUTH_TOKEN_HEADER = "x-helpdesk-internal-token"
CALLER_HEADER = "x-helpdesk-caller"
CORRELATION_ID_HEADER = "x-correlation-id"
ACTOR_TELEGRAM_USER_ID_HEADER = "x-helpdesk-actor-telegram-user-id"


@dataclass(slots=True, frozen=True)
class BackendRequestContext:
    caller: str
    correlation_id: str
    actor: RequestActor | None = None


def build_call_metadata(
    *,
    auth_config: BackendAuthConfig,
    correlation_id: str,
    actor: RequestActor | None = None,
) -> tuple[tuple[str, str], ...]:
    metadata: list[tuple[str, str]] = [
        (INTERNAL_AUTH_TOKEN_HEADER, auth_config.token.strip()),
        (CALLER_HEADER, auth_config.caller.strip() or "telegram-bot"),
        (CORRELATION_ID_HEADER, correlation_id),
    ]
    if actor is not None:
        metadata.append((ACTOR_TELEGRAM_USER_ID_HEADER, str(actor.telegram_user_id)))
    return tuple(metadata)


def resolve_backend_request_context(
    context: grpc.aio.ServicerContext,
    *,
    auth_config: BackendAuthConfig,
    fallback_actor: RequestActor | None = None,
) -> BackendRequestContext:
    metadata = {item.key.lower(): item.value for item in context.invocation_metadata()}

    provided_token = metadata.get(INTERNAL_AUTH_TOKEN_HEADER)
    if not provided_token or provided_token != auth_config.token.strip():
        raise PermissionError("Внутренний backend запрос отклонён.")

    caller = metadata.get(CALLER_HEADER, "unknown")
    correlation_id = metadata.get(CORRELATION_ID_HEADER, "")
    actor = fallback_actor

    metadata_actor_id = metadata.get(ACTOR_TELEGRAM_USER_ID_HEADER)
    if metadata_actor_id is not None:
        try:
            resolved_actor = RequestActor(telegram_user_id=int(metadata_actor_id))
        except ValueError as exc:
            raise ValueError("Некорректный идентификатор internal actor.") from exc
        if actor is not None and actor.telegram_user_id != resolved_actor.telegram_user_id:
            raise ValueError("Actor transport metadata не совпадает с protobuf request.")
        actor = resolved_actor

    if not correlation_id:
        from infrastructure.runtime_context import ensure_correlation_id

        correlation_id = ensure_correlation_id()

    return BackendRequestContext(
        caller=caller,
        correlation_id=correlation_id,
        actor=actor,
    )
