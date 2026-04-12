from __future__ import annotations

import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from application.ai.summaries import (
    AIPredictionConfidence,
    TicketAssistSnapshot,
    TicketCategoryPrediction,
    TicketMacroSuggestion,
    TicketSummaryStatus,
)
from application.contracts.actors import RequestActor
from application.contracts.ai import PredictTicketCategoryCommand
from application.contracts.tickets import ClientTicketMessageCommand
from application.services.helpdesk.service import HelpdeskService, HelpdeskServiceFactory
from application.services.stats import (
    AnalyticsCategorySnapshot,
    AnalyticsOperatorSnapshot,
    AnalyticsRatingBucket,
    AnalyticsWindow,
    HelpdeskAnalyticsSnapshot,
    OperatorTicketLoad,
)
from application.use_cases.tickets.summaries import HistoricalTicketSummary, TicketSummary
from backend.grpc.client import build_helpdesk_backend_client_factory
from backend.grpc.server import build_helpdesk_backend_server
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketAttachmentKind, TicketStatus
from infrastructure.config.settings import BackendAuthConfig, BackendServiceConfig, ResilienceConfig


@asynccontextmanager
async def _build_service_factory(service: object) -> AsyncIterator[HelpdeskService]:
    yield cast(HelpdeskService, service)


async def test_helpdesk_grpc_client_roundtrips_ticket_commands_and_analytics() -> None:
    ticket_public_id = uuid4()
    command_log: list[ClientTicketMessageCommand] = []
    service = SimpleNamespace(
        create_ticket_from_client_intake=_capture_create_call(command_log, ticket_public_id),
        get_ticket_ai_assist_snapshot=_build_ticket_assist_call(),
        predict_ticket_category=_build_category_prediction_call(),
        get_analytics_snapshot=_build_analytics_call(),
        list_archived_tickets=_build_archived_tickets_call(ticket_public_id),
    )
    helpdesk_service_factory = cast(
        HelpdeskServiceFactory,
        lambda: _build_service_factory(service),
    )
    port = _reserve_tcp_port()
    server = build_helpdesk_backend_server(
        helpdesk_service_factory=helpdesk_service_factory,
        bind_target=f"127.0.0.1:{port}",
        auth_config=BackendAuthConfig(token="internal-test-token", caller="test-client"),
    )
    await server.start()

    client_factory = build_helpdesk_backend_client_factory(
        BackendServiceConfig(host="127.0.0.1", port=port),
        auth_config=BackendAuthConfig(token="internal-test-token", caller="test-client"),
        resilience_config=ResilienceConfig(),
    )

    try:
        async with client_factory() as client:
            service_name, status = await client.get_backend_status()
            ticket = await client.create_ticket_from_client_intake(
                ClientTicketMessageCommand(
                    client_chat_id=2002,
                    telegram_message_id=15,
                    text="Не открывается доступ",
                    attachment=TicketAttachmentDetails(
                        kind=TicketAttachmentKind.DOCUMENT,
                        telegram_file_id="file-1",
                        telegram_file_unique_id="unique-1",
                        filename="issue.txt",
                        mime_type="text/plain",
                        storage_path="document/unique-1.txt",
                    ),
                    category_id=2,
                )
            )
            snapshot = await client.get_analytics_snapshot(
                window=AnalyticsWindow.DAYS_7,
                actor=RequestActor(telegram_user_id=1001),
            )
            ticket_assist = await client.get_ticket_ai_assist_snapshot(
                ticket_public_id=ticket_public_id,
                refresh_summary=True,
                actor=RequestActor(telegram_user_id=1001),
            )
            category_prediction = await client.predict_ticket_category(
                PredictTicketCategoryCommand(text="Не удаётся войти после смены пароля"),
                actor=RequestActor(telegram_user_id=2002),
            )
            archived_tickets = await client.list_archived_tickets(
                actor=RequestActor(telegram_user_id=1001),
            )
    finally:
        await server.stop()

    assert service_name == "helpdesk-backend"
    assert status == "ready"
    assert ticket.public_id == ticket_public_id
    assert ticket.status == TicketStatus.QUEUED
    assert command_log[0].attachment is not None
    assert command_log[0].attachment.storage_path == "document/unique-1.txt"
    assert command_log[0].category_id == 2
    assert snapshot.window == AnalyticsWindow.DAYS_7
    assert snapshot.feedback_count == 4
    assert ticket_assist is not None
    assert ticket_assist.short_summary == "Клиент потерял доступ после смены пароля."
    assert ticket_assist.summary_status is TicketSummaryStatus.FRESH
    assert ticket_assist.macro_suggestions[0].macro_id == 11
    assert category_prediction.category_id == 2
    assert category_prediction.confidence == AIPredictionConfidence.HIGH
    assert archived_tickets[0].public_id == ticket_public_id
    assert archived_tickets[0].mini_title == "Не могу войти в кабинет после обновления пароля"


async def test_helpdesk_grpc_rejects_invalid_internal_token() -> None:
    helpdesk_service_factory = cast(
        HelpdeskServiceFactory,
        lambda: _build_service_factory(SimpleNamespace()),
    )
    port = _reserve_tcp_port()
    server = build_helpdesk_backend_server(
        helpdesk_service_factory=helpdesk_service_factory,
        bind_target=f"127.0.0.1:{port}",
        auth_config=BackendAuthConfig(token="expected-token", caller="test-client"),
    )
    await server.start()

    client_factory = build_helpdesk_backend_client_factory(
        BackendServiceConfig(host="127.0.0.1", port=port),
        auth_config=BackendAuthConfig(token="wrong-token", caller="test-client"),
        resilience_config=ResilienceConfig(),
    )

    try:
        async with client_factory() as client:
            try:
                await client.get_backend_status()
            except PermissionError as exc:
                assert "отклонён" in str(exc)
            else:
                raise AssertionError("expected PermissionError")
    finally:
        await server.stop()


def _capture_create_call(
    command_log: list[ClientTicketMessageCommand],
    ticket_public_id: Any,
) -> Any:
    async def call(command: ClientTicketMessageCommand) -> TicketSummary:
        command_log.append(command)
        return TicketSummary(
            public_id=ticket_public_id,
            public_number="HD-AAAA1111",
            status=TicketStatus.QUEUED,
            created=True,
        )

    return call


def _build_analytics_call() -> Any:
    async def call(
        *,
        window: AnalyticsWindow,
        actor: RequestActor | None = None,
    ) -> HelpdeskAnalyticsSnapshot:
        assert actor == RequestActor(telegram_user_id=1001)
        return HelpdeskAnalyticsSnapshot(
            window=window,
            total_open_tickets=6,
            queued_tickets_count=2,
            assigned_tickets_count=3,
            escalated_tickets_count=1,
            closed_tickets_count=4,
            tickets_per_operator=(
                OperatorTicketLoad(operator_id=7, display_name="Operator One", ticket_count=3),
            ),
            period_created_tickets_count=9,
            period_closed_tickets_count=5,
            average_first_response_time_seconds=126,
            average_resolution_time_seconds=7260,
            satisfaction_average=4.7,
            feedback_count=4,
            feedback_coverage_percent=80,
            rating_distribution=(AnalyticsRatingBucket(rating=5, count=3),),
            operator_snapshots=(
                AnalyticsOperatorSnapshot(
                    operator_id=7,
                    display_name="Operator One",
                    active_ticket_count=3,
                    closed_ticket_count=4,
                    average_first_response_time_seconds=120,
                    average_resolution_time_seconds=5400,
                    average_satisfaction=4.8,
                    feedback_count=3,
                ),
            ),
            category_snapshots=(
                AnalyticsCategorySnapshot(
                    category_id=1,
                    category_title="Доступ и вход",
                    created_ticket_count=5,
                    open_ticket_count=2,
                    closed_ticket_count=3,
                    average_satisfaction=4.5,
                    feedback_count=2,
                    sla_breach_count=2,
                ),
            ),
            best_operators_by_closures=(),
            best_operators_by_satisfaction=(),
            top_categories=(),
            first_response_breach_count=2,
            resolution_breach_count=1,
            sla_categories=(),
        )

    return call


def _build_ticket_assist_call() -> Any:
    async def call(
        *,
        ticket_public_id: Any,
        refresh_summary: bool = False,
        actor: RequestActor | None = None,
    ) -> TicketAssistSnapshot:
        assert actor == RequestActor(telegram_user_id=1001)
        assert ticket_public_id is not None
        assert refresh_summary is True
        return TicketAssistSnapshot(
            available=True,
            summary_status=TicketSummaryStatus.FRESH,
            short_summary="Клиент потерял доступ после смены пароля.",
            user_goal="Хочет быстро восстановить вход без новой регистрации.",
            actions_taken="Оператор проверил карточку профиля и подготовил сброс доступа.",
            current_status="Ожидается подтверждение входа после обновления ссылки.",
            macro_suggestions=(
                TicketMacroSuggestion(
                    macro_id=11,
                    title="Сброс доступа",
                    body="Сбросили пароль и обновили ссылку.",
                    reason="Подходит под типовой сценарий восстановления входа.",
                    confidence=AIPredictionConfidence.HIGH,
                ),
            ),
            model_id="Qwen/Qwen3.5-4B",
        )

    return call


def _build_category_prediction_call() -> Any:
    async def call(
        command: PredictTicketCategoryCommand,
        *,
        actor: RequestActor | None = None,
    ) -> TicketCategoryPrediction:
        assert actor == RequestActor(telegram_user_id=2002)
        assert command.text == "Не удаётся войти после смены пароля"
        return TicketCategoryPrediction(
            available=True,
            category_id=2,
            category_code="access",
            category_title="Доступ и вход",
            confidence=AIPredictionConfidence.HIGH,
            reason="В тексте явный запрос на восстановление доступа.",
            model_id="Qwen/Qwen3.5-4B",
        )

    return call


def _build_archived_tickets_call(ticket_public_id: Any) -> Any:
    async def call(
        *,
        limit: int | None = None,
        offset: int = 0,
        actor: RequestActor | None = None,
    ) -> tuple[HistoricalTicketSummary, ...]:
        assert actor == RequestActor(telegram_user_id=1001)
        assert limit is None
        assert offset == 0
        return (
            HistoricalTicketSummary(
                public_id=ticket_public_id,
                public_number="HD-AAAA1111",
                status=TicketStatus.CLOSED,
                created_at=datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
                closed_at=datetime(2026, 4, 7, 11, 45, tzinfo=UTC),
                mini_title="Не могу войти в кабинет после обновления пароля",
                category_id=2,
                category_code="access",
                category_title="Доступ и вход",
            ),
        )

    return call


def _reserve_tcp_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return cast(int, sock.getsockname()[1])
    except PermissionError as exc:
        pytest.skip(f"Sandbox blocks local TCP sockets: {exc}")
