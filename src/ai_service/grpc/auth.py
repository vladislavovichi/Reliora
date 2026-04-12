from __future__ import annotations

from dataclasses import dataclass

import grpc

from infrastructure.config.settings import AIServiceAuthConfig

INTERNAL_AUTH_TOKEN_HEADER = "x-helpdesk-internal-token"
CALLER_HEADER = "x-helpdesk-caller"
CORRELATION_ID_HEADER = "x-correlation-id"


@dataclass(slots=True, frozen=True)
class AIServiceRequestContext:
    caller: str
    correlation_id: str


def build_call_metadata(
    *,
    auth_config: AIServiceAuthConfig,
    correlation_id: str,
) -> tuple[tuple[str, str], ...]:
    return (
        (INTERNAL_AUTH_TOKEN_HEADER, auth_config.token.strip()),
        (CALLER_HEADER, auth_config.caller.strip() or "helpdesk-backend"),
        (CORRELATION_ID_HEADER, correlation_id),
    )


def resolve_ai_service_request_context(
    context: grpc.aio.ServicerContext,
    *,
    auth_config: AIServiceAuthConfig,
) -> AIServiceRequestContext:
    metadata = {item.key.lower(): item.value for item in context.invocation_metadata()}

    provided_token = metadata.get(INTERNAL_AUTH_TOKEN_HEADER)
    if not provided_token or provided_token != auth_config.token.strip():
        raise PermissionError("Внутренний ai-service запрос отклонён.")

    correlation_id = metadata.get(CORRELATION_ID_HEADER, "")
    if not correlation_id:
        from infrastructure.runtime_context import ensure_correlation_id

        correlation_id = ensure_correlation_id()

    return AIServiceRequestContext(
        caller=metadata.get(CALLER_HEADER, "unknown"),
        correlation_id=correlation_id,
    )
