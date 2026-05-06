from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock
from uuid import UUID, uuid4

from application.contracts.actors import RequestActor
from application.use_cases.tickets.exports import (
    TicketReport,
    TicketReportExport,
    TicketReportFormat,
)
from application.use_cases.tickets.summaries import TicketDetailsSummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.handlers.operator.workflow_ticket_exports import (
    handle_export_action,
    handle_export_file_action,
)
from bot.texts.operator import build_export_opened_text, build_export_ready_text
from domain.enums.tickets import TicketStatus
from tests.support.aiogram import CallbackHarness, build_callback_harness
from tests.support.backend import FakeHelpdeskBackendClient, build_backend_client_factory


class TicketExportBackendClient(FakeHelpdeskBackendClient):
    def __init__(
        self,
        *,
        ticket_details: TicketDetailsSummary | None = None,
        ticket_export: TicketReportExport | None = None,
    ) -> None:
        self._ticket_details = ticket_details
        self._ticket_export = ticket_export
        self.get_ticket_details_mock = AsyncMock()
        self.export_ticket_report_mock = AsyncMock()

    async def get_ticket_details(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketDetailsSummary | None:
        await self.get_ticket_details_mock(ticket_public_id=ticket_public_id, actor=actor)
        return self._ticket_details

    async def export_ticket_report(
        self,
        *,
        ticket_public_id: UUID,
        format: TicketReportFormat,
        actor: RequestActor | None = None,
    ) -> TicketReportExport | None:
        await self.export_ticket_report_mock(
            ticket_public_id=ticket_public_id,
            format=format,
            actor=actor,
        )
        return self._ticket_export


def _build_helpdesk_backend_client_factory(
    service: FakeHelpdeskBackendClient,
) -> HelpdeskBackendClientFactory:
    return build_backend_client_factory(service)


def _build_callback(*, ticket_public_id: str) -> CallbackHarness:
    return build_callback_harness(
        user_id=1001,
        data=f"operator:export:{ticket_public_id}",
        with_edit_text=True,
    )


async def test_export_action_opens_export_surface() -> None:
    ticket_public_id = uuid4()
    callback = _build_callback(ticket_public_id=str(ticket_public_id))
    ticket_details = TicketDetailsSummary(
        public_id=ticket_public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        status=TicketStatus.ASSIGNED,
        priority="high",
        subject="Нужна помощь с доступом",
        assigned_operator_id=7,
        assigned_operator_name="Иван Петров",
        assigned_operator_telegram_user_id=1001,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
        tags=("vip",),
        last_message_text="Не могу войти",
        last_message_sender_type=None,
        message_history=(),
    )
    service = TicketExportBackendClient(ticket_details=ticket_details)
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    operator_presence = SimpleNamespace(touch=AsyncMock())
    operator_active_ticket_store = SimpleNamespace(
        set_active_ticket=AsyncMock(),
        clear_if_matches=AsyncMock(),
    )
    ticket_live_session_store = SimpleNamespace(refresh_session=AsyncMock())

    await handle_export_action(
        callback=callback.callback,
        callback_data=SimpleNamespace(ticket_public_id=str(ticket_public_id)),
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
        operator_active_ticket_store=operator_active_ticket_store,
        ticket_live_session_store=ticket_live_session_store,
    )

    callback.answer.assert_awaited_once_with(build_export_opened_text(ticket_details.public_number))
    assert callback.message.edit_text is not None
    callback.message.edit_text.assert_awaited_once_with(ANY, reply_markup=ANY)


async def test_export_file_action_sends_document_to_operator_chat() -> None:
    ticket_public_id = uuid4()
    callback = _build_callback(ticket_public_id=str(ticket_public_id))
    bot = Mock()
    bot.send_document = AsyncMock()
    report = TicketReport(
        public_id=ticket_public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        status=TicketStatus.CLOSED,
        priority="high",
        subject="Нужна помощь с доступом",
        assigned_operator_id=7,
        assigned_operator_name="Иван Петров",
        assigned_operator_telegram_user_id=1001,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 8, 13, 0, tzinfo=UTC),
        first_response_at=datetime(2026, 4, 8, 12, 10, tzinfo=UTC),
        first_response_seconds=600,
        closed_at=datetime(2026, 4, 8, 14, 0, tzinfo=UTC),
        category_code="access",
        category_title="Доступ и вход",
        sentiment=None,
        sentiment_confidence=None,
        sentiment_reason=None,
        sentiment_detected_at=None,
        tags=("vip",),
        feedback=None,
        messages=(),
        events=(),
    )
    ticket_export = TicketReportExport(
        format=TicketReportFormat.CSV,
        filename="ticket-report-hd-aaaa1111.csv",
        content_type="text/csv",
        content=b"ticket_public_number\nHD-AAAA1111\n",
        report=report,
    )
    service = TicketExportBackendClient(ticket_export=ticket_export)
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    operator_presence = SimpleNamespace(touch=AsyncMock())

    await handle_export_file_action(
        callback=callback.callback,
        callback_data=SimpleNamespace(
            ticket_public_id=str(ticket_public_id),
            action="export_csv",
        ),
        bot=bot,
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
    )

    callback.answer.assert_awaited_once_with(
        build_export_ready_text(ticket_export.report.public_number, format_name="CSV")
    )
    _, kwargs = bot.send_document.await_args
    assert kwargs["caption"] == "Отчёт по заявке HD-AAAA1111"
    assert kwargs["document"].filename == "ticket-report-hd-aaaa1111.csv"
