import asyncio
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

import grpc

from ai_service.grpc.client import build_ai_service_client_factory
from application.contracts.ai import AIContextMessage, GenerateTicketSummaryCommand
from application.errors import AIUnavailableError, ForbiddenError, ValidationAppError
from domain.enums.tickets import TicketMessageSenderType, TicketStatus
from infrastructure.config.settings import get_settings
from infrastructure.logging import configure_logging


async def run() -> int:
    settings = get_settings()
    configure_logging(settings.logging, app=settings.app)
    model_id = settings.ai.effective_model_id
    model_loaded = False

    grpc_status = "unavailable"
    connectivity_ok = False
    completion_success = False
    failure_reason: str | None = None
    started_at = perf_counter()

    try:
        async with build_ai_service_client_factory(
            settings.ai_service,
            auth_config=settings.ai_service_auth,
            resilience_config=settings.resilience,
        )() as client:
            status = await client.get_service_status()
            grpc_status = f"{status.service}/{status.status}"
            model_id = status.model_id or model_id
            model_loaded = status.model_loaded
            connectivity_ok = (
                status.service == "helpdesk-ai-service"
                and status.status == "ready"
                and status.model_loaded
            )
            result = await client.generate_ticket_summary(_build_smoke_command())
            completion_success = bool(result.available and result.summary is not None)
            failure_reason = result.failure_reason
            if not completion_success and failure_reason is None:
                failure_reason = "unknown"
    except (TimeoutError, AIUnavailableError) as exc:
        failure_reason = f"grpc_unavailable:{exc.__class__.__name__}"
    except ForbiddenError as exc:
        failure_reason = f"grpc_unavailable:{exc.__class__.__name__}"
    except ValidationAppError as exc:
        failure_reason = f"schema_validation_failed:{exc.__class__.__name__}"
    except grpc.RpcError as exc:
        failure_reason = f"grpc_unavailable:{exc.__class__.__name__}"
    except Exception as exc:
        failure_reason = f"unknown:{exc.__class__.__name__}"

    latency_ms = round((perf_counter() - started_at) * 1000, 2)
    print("AI provider: local")
    print(f"model_loaded: {str(model_loaded).lower()}")
    print(f"model_id: {model_id or '-'}")
    print("operation: summary")
    print(f"gRPC connectivity/status: {str(connectivity_ok).lower()} {grpc_status}")
    print(f"real completion success: {str(completion_success).lower()}")
    print(f"latency_ms: {latency_ms}")
    if failure_reason:
        print(f"failure_reason: {failure_reason}")

    return 0 if completion_success else 1


def _build_smoke_command() -> GenerateTicketSummaryCommand:
    return GenerateTicketSummaryCommand(
        ticket_public_id=uuid4(),
        subject="Проверка AI smoke",
        status=TicketStatus.ASSIGNED,
        category_title="Доступ",
        message_history=(
            AIContextMessage(
                sender_type=TicketMessageSenderType.CLIENT,
                sender_label=None,
                text="Здравствуйте, не могу войти в личный кабинет после смены пароля.",
                created_at=datetime.now(UTC),
            ),
        ),
    )


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
