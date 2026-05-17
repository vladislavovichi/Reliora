from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx

from application.contracts.actors import RequestActor
from application.services.stats import AnalyticsWindow, HelpdeskAnalyticsSnapshot
from application.use_cases.tickets.summaries import (
    HistoricalTicketSummary,
    OperatorTicketSummary,
    QueuedTicketSummary,
    TicketDetailsSummary,
    TicketMessageSummary,
)
from backend.grpc.contracts import HelpdeskBackendClientFactory
from domain.enums.roles import UserRole
from domain.enums.tickets import TicketMessageSenderType, TicketSentiment, TicketStatus
from infrastructure.config.settings import MiniAppConfig
from mini_app.api import MiniAppGateway
from mini_app.auth import TelegramMiniAppUser
from mini_app.context import MiniAppAuthenticatedContext, load_mini_app_session
from mini_app.http import create_mini_app
from mini_app.launch import ResolvedMiniAppLaunch
from mini_app.serializers import serialize_dashboard_bucket, serialize_dashboard_ticket_preview
from tests.support.backend import FakeHelpdeskBackendClient, build_backend_client_factory


async def test_operator_dashboard_bucket_counts_use_available_ticket_data() -> None:
    queued_id = uuid4()
    escalated_id = uuid4()
    assigned_id = uuid4()
    client = StubDashboardBackendClient(
        queued=(_queued_ticket(queued_id, subject="Cannot sign in", category_title=None),),
        mine=(
            _operator_ticket(
                escalated_id,
                subject="Angry customer",
                status=TicketStatus.ESCALATED,
                category_title="Access",
            ),
            _operator_ticket(
                assigned_id,
                subject="Billing question",
                status=TicketStatus.ASSIGNED,
                category_title="Billing",
            ),
        ),
        details={
            queued_id: _ticket_details(
                queued_id,
                subject="Cannot sign in",
                status=TicketStatus.QUEUED,
                category_title=None,
            ),
            escalated_id: _ticket_details(
                escalated_id,
                subject="Angry customer",
                status=TicketStatus.ESCALATED,
                category_title="Access",
                assigned_operator_name="Anna",
                sentiment=TicketSentiment.FRUSTRATED,
                last_message_sender_type=TicketMessageSenderType.CLIENT,
            ),
            assigned_id: _ticket_details(
                assigned_id,
                subject="Billing question",
                status=TicketStatus.ASSIGNED,
                category_title="Billing",
                assigned_operator_name="Anna",
                last_message_sender_type=TicketMessageSenderType.OPERATOR,
            ),
        },
    )
    gateway = MiniAppGateway(backend_client_factory=_backend_factory(client))

    result = await gateway.get_operator_dashboard(user=_mini_app_user(telegram_user_id=1001))

    buckets = result["buckets"]
    assert buckets["unassigned_open_tickets"]["count"] == 1
    assert buckets["my_active_tickets"]["count"] == 2
    assert buckets["escalated_tickets"]["count"] == 1
    assert buckets["negative_sentiment_tickets"]["count"] == 1
    assert buckets["tickets_without_operator_reply"]["count"] == 1
    assert buckets["tickets_without_category"]["count"] == 1
    assert buckets["sla_breached_tickets"]["count"] == 0
    assert buckets["sla_breached_tickets"]["unavailable_reason"]


async def test_operator_dashboard_is_scoped_to_current_operator() -> None:
    client = StubDashboardBackendClient(mine=())
    gateway = MiniAppGateway(backend_client_factory=_backend_factory(client))

    await gateway.get_operator_dashboard(user=_mini_app_user(telegram_user_id=2002))

    assert client.operator_ticket_calls == [2002]


async def test_operator_dashboard_degrades_when_details_are_missing() -> None:
    queued_id = uuid4()
    mine_id = uuid4()
    client = StubDashboardBackendClient(
        queued=(_queued_ticket(queued_id, subject="No detail", category_title=None),),
        mine=(_operator_ticket(mine_id, subject="Mine without detail", category_title=None),),
        details={},
    )
    gateway = MiniAppGateway(backend_client_factory=_backend_factory(client))

    result = await gateway.get_operator_dashboard(user=_mini_app_user(telegram_user_id=1001))

    buckets = result["buckets"]
    assert buckets["unassigned_open_tickets"]["count"] == 1
    assert buckets["my_active_tickets"]["count"] == 1
    assert buckets["negative_sentiment_tickets"]["count"] == 0
    assert buckets["tickets_without_operator_reply"]["count"] == 0
    assert buckets["tickets_without_category"]["count"] == 2


def test_dashboard_serializer_builds_ticket_preview_with_optional_signals() -> None:
    ticket_id = uuid4()
    ticket = _ticket_details(
        ticket_id,
        subject="Need refund",
        category_title="Billing",
        assigned_operator_name="Anna",
        sentiment=TicketSentiment.ESCALATION_RISK,
        last_message_sender_type=TicketMessageSenderType.CLIENT,
    )

    preview = serialize_dashboard_ticket_preview(ticket)
    bucket = serialize_dashboard_bucket(
        key="negative_sentiment_tickets",
        label="Negative tone",
        tickets=[ticket],
        route="mine",
        severity="warning",
    )

    assert preview["public_id"] == str(ticket_id)
    assert preview["category"] == "Billing"
    assert preview["assigned_operator"]["name"] == "Anna"
    assert preview["sentiment"]["value"] == "escalation_risk"
    assert preview["last_activity_at"] == "2026-04-20T10:05:00+00:00"
    assert bucket["count"] == 1
    assert bucket["tickets"][0]["subject"] == "Need refund"


def test_operator_dashboard_route_authorization(tmp_path: Path) -> None:
    gateway = StubGateway()
    response = _request_dashboard(gateway=gateway, static_dir=tmp_path, role=UserRole.USER)

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert gateway.called is False

    response = _request_dashboard(gateway=gateway, static_dir=tmp_path, role=UserRole.OPERATOR)

    assert response.status_code == HTTPStatus.OK
    assert gateway.called is True
    assert response.json()["buckets"] == {}


class StubDashboardBackendClient(FakeHelpdeskBackendClient):
    def __init__(
        self,
        *,
        queued: tuple[QueuedTicketSummary, ...] = (),
        mine: tuple[OperatorTicketSummary, ...] = (),
        details: dict[UUID, TicketDetailsSummary] | None = None,
    ) -> None:
        self.queued = queued
        self.mine = mine
        self.details = details or {}
        self.operator_ticket_calls: list[int] = []

    async def get_analytics_snapshot(
        self,
        *,
        window: AnalyticsWindow,
        actor: RequestActor | None = None,
    ) -> HelpdeskAnalyticsSnapshot:
        del actor
        return _analytics_snapshot(window=window)

    async def list_queued_tickets(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> tuple[QueuedTicketSummary, ...]:
        del actor
        return self.queued

    async def list_operator_tickets(
        self,
        *,
        operator_telegram_user_id: int,
        actor: RequestActor | None = None,
    ) -> tuple[OperatorTicketSummary, ...]:
        del actor
        self.operator_ticket_calls.append(operator_telegram_user_id)
        return self.mine

    async def list_archived_tickets(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> tuple[HistoricalTicketSummary, ...]:
        del actor
        return ()

    async def get_ticket_details(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketDetailsSummary | None:
        del actor
        return self.details.get(ticket_public_id)


class StubGateway:
    def __init__(self) -> None:
        self.called = False

    async def get_operator_dashboard(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        del user
        self.called = True
        return {"buckets": {}, "sections": {}}


def _backend_factory(client: StubDashboardBackendClient) -> HelpdeskBackendClientFactory:
    return build_backend_client_factory(client)


def _queued_ticket(
    public_id: UUID,
    *,
    subject: str,
    category_title: str | None,
) -> QueuedTicketSummary:
    return QueuedTicketSummary(
        public_id=public_id,
        public_number=f"#{str(public_id)[:8]}",
        subject=subject,
        priority="normal",
        status=TicketStatus.QUEUED,
        category_title=category_title,
    )


def _operator_ticket(
    public_id: UUID,
    *,
    subject: str,
    status: TicketStatus = TicketStatus.ASSIGNED,
    category_title: str | None,
) -> OperatorTicketSummary:
    return OperatorTicketSummary(
        public_id=public_id,
        public_number=f"#{str(public_id)[:8]}",
        subject=subject,
        priority="high",
        status=status,
        category_title=category_title,
    )


def _ticket_details(
    public_id: UUID,
    *,
    subject: str,
    status: TicketStatus = TicketStatus.ASSIGNED,
    category_title: str | None,
    assigned_operator_name: str | None = None,
    sentiment: TicketSentiment | None = None,
    last_message_sender_type: TicketMessageSenderType | None = None,
) -> TicketDetailsSummary:
    message_history: tuple[TicketMessageSummary, ...] = ()
    if last_message_sender_type is not None:
        message_history = (
            TicketMessageSummary(
                sender_type=last_message_sender_type,
                sender_operator_id=(
                    7 if last_message_sender_type == TicketMessageSenderType.OPERATOR else None
                ),
                sender_operator_name=(
                    assigned_operator_name
                    if last_message_sender_type == TicketMessageSenderType.OPERATOR
                    else None
                ),
                text="Latest update",
                created_at=datetime(2026, 4, 20, 10, 5, tzinfo=UTC),
            ),
        )
    return TicketDetailsSummary(
        public_id=public_id,
        public_number=f"#{str(public_id)[:8]}",
        client_chat_id=3001,
        status=status,
        priority="high",
        subject=subject,
        assigned_operator_id=7 if assigned_operator_name else None,
        assigned_operator_name=assigned_operator_name,
        assigned_operator_telegram_user_id=1001 if assigned_operator_name else None,
        assigned_operator_username="anna" if assigned_operator_name else None,
        created_at=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 20, 10, 5, tzinfo=UTC),
        category_id=1 if category_title else None,
        category_code="topic" if category_title else None,
        category_title=category_title,
        sentiment=sentiment,
        sentiment_detected_at=(
            datetime(2026, 4, 20, 10, 4, tzinfo=UTC) if sentiment is not None else None
        ),
        last_message_sender_type=last_message_sender_type,
        message_history=message_history,
    )


def _analytics_snapshot(*, window: AnalyticsWindow) -> HelpdeskAnalyticsSnapshot:
    return HelpdeskAnalyticsSnapshot(
        window=window,
        total_open_tickets=3,
        queued_tickets_count=1,
        assigned_tickets_count=1,
        escalated_tickets_count=1,
        closed_tickets_count=0,
        tickets_per_operator=(),
        period_created_tickets_count=3,
        period_closed_tickets_count=0,
        average_first_response_time_seconds=None,
        average_resolution_time_seconds=None,
        satisfaction_average=None,
        feedback_count=0,
        feedback_coverage_percent=None,
        rating_distribution=(),
        operator_snapshots=(),
        category_snapshots=(),
        best_operators_by_closures=(),
        best_operators_by_satisfaction=(),
        top_categories=(),
        first_response_breach_count=0,
        resolution_breach_count=0,
        sla_categories=(),
    )


def _mini_app_user(*, telegram_user_id: int) -> TelegramMiniAppUser:
    return TelegramMiniAppUser(
        telegram_user_id=telegram_user_id,
        first_name="Anna",
        last_name=None,
        username="anna",
        language_code="ru",
    )


def _request_dashboard(*, gateway: StubGateway, static_dir: Path, role: UserRole) -> Any:
    app = create_mini_app(
        gateway=gateway,  # type: ignore[arg-type]
        config=MiniAppConfig(listen_host="127.0.0.1", port=0, init_data_ttl_seconds=3600),
        bot_token="123:ABC",
        static_dir=static_dir,
    )

    async def load_session_override() -> MiniAppAuthenticatedContext:
        return MiniAppAuthenticatedContext(
            launch=ResolvedMiniAppLaunch(
                init_data="signed",
                source="test",
                client_source=None,
                diagnostics=(),
                is_telegram_webapp=True,
                has_telegram_user=True,
                attempted_sources=(),
                client_platform=None,
                client_version=None,
            ),
            user=_mini_app_user(telegram_user_id=1001),
            session={
                "access": {"telegram_user_id": 1001, "role": role.value},
                "user": {"telegram_user_id": 1001, "display_name": "Anna"},
            },
            gateway=gateway,  # type: ignore[arg-type]
        )

    app.dependency_overrides[load_mini_app_session] = load_session_override
    return asyncio.run(_get_asgi(app, "/api/dashboard/operator"))


async def _get_asgi(app: Any, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://mini-app.test") as client:
        return await client.get(path)
