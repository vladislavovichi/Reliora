from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from application.contracts.actors import RequestActor
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
from application.use_cases.tickets.summaries import TicketSummary
from backend.grpc.client import LocalHelpdeskGrpcClient
from backend.grpc.server import LocalHelpdeskGrpcServer
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketAttachmentKind, TicketStatus


@asynccontextmanager
async def _build_service_factory(service: object) -> AsyncIterator[HelpdeskService]:
    yield cast(HelpdeskService, service)


async def test_local_helpdesk_grpc_client_roundtrips_ticket_commands_and_analytics() -> None:
    ticket_public_id = uuid4()
    command_log: list[ClientTicketMessageCommand] = []
    service = SimpleNamespace(
        create_ticket_from_client_intake=_capture_create_call(command_log, ticket_public_id),
        get_analytics_snapshot=_build_analytics_call(),
    )
    helpdesk_service_factory = cast(
        HelpdeskServiceFactory,
        lambda: _build_service_factory(service),
    )
    server = LocalHelpdeskGrpcServer(helpdesk_service_factory=helpdesk_service_factory)
    client = LocalHelpdeskGrpcClient(server=server)

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

    assert ticket.public_id == ticket_public_id
    assert ticket.status == TicketStatus.QUEUED
    assert command_log[0].attachment is not None
    assert command_log[0].attachment.storage_path == "document/unique-1.txt"
    assert command_log[0].category_id == 2
    assert snapshot.window == AnalyticsWindow.DAYS_7
    assert snapshot.feedback_count == 4


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
