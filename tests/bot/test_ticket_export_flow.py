from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

from aiogram.types import CallbackQuery, Chat, Message, User

from application.use_cases.tickets.exports import (
    TicketReport,
    TicketReportExport,
    TicketReportFormat,
)
from application.use_cases.tickets.summaries import TicketDetailsSummary
from backend.grpc.contracts import HelpdeskBackendClient, HelpdeskBackendClientFactory
from bot.handlers.operator.workflow_ticket_exports import (
    handle_export_action,
    handle_export_file_action,
)
from bot.texts.operator import build_export_opened_text, build_export_ready_text
from domain.enums.tickets import TicketStatus


def _build_helpdesk_backend_client_factory(service: object) -> HelpdeskBackendClientFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[HelpdeskBackendClient]:
        yield cast(HelpdeskBackendClient, service)

    return provide


def _build_callback(*, ticket_public_id: str) -> CallbackQuery:
    message = Message.model_construct(
        message_id=10,
        date=datetime.now(UTC),
        chat=Chat.model_construct(id=3001, type="private"),
        from_user=User.model_construct(id=1001, is_bot=False, first_name="Operator"),
        text="stub",
    )
    object.__setattr__(message, "answer", AsyncMock())
    object.__setattr__(message, "edit_text", AsyncMock())

    callback = CallbackQuery.model_construct(
        id="callback-id",
        from_user=User.model_construct(id=1001, is_bot=False, first_name="Operator"),
        chat_instance="chat-instance",
        data=f"operator:export:{ticket_public_id}",
        message=message,
    )
    object.__setattr__(callback, "answer", AsyncMock())
    return callback


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
    service = SimpleNamespace(get_ticket_details=AsyncMock(return_value=ticket_details))
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    operator_presence = SimpleNamespace(touch=AsyncMock())
    operator_active_ticket_store = SimpleNamespace(
        set_active_ticket=AsyncMock(),
        clear_if_matches=AsyncMock(),
    )
    ticket_live_session_store = SimpleNamespace(refresh_session=AsyncMock())

    await handle_export_action(
        callback=callback,
        callback_data=SimpleNamespace(ticket_public_id=str(ticket_public_id)),
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
        operator_active_ticket_store=operator_active_ticket_store,
        ticket_live_session_store=ticket_live_session_store,
    )

    callback_answer_mock(callback).assert_awaited_once_with(
        build_export_opened_text(ticket_details.public_number)
    )
    message_edit_text_mock(callback).assert_awaited_once_with(ANY, reply_markup=ANY)


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
    service = SimpleNamespace(export_ticket_report=AsyncMock(return_value=ticket_export))
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    operator_presence = SimpleNamespace(touch=AsyncMock())

    await handle_export_file_action(
        callback=callback,
        callback_data=SimpleNamespace(
            ticket_public_id=str(ticket_public_id),
            action="export_csv",
        ),
        bot=bot,
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
    )

    callback_answer_mock(callback).assert_awaited_once_with(
        build_export_ready_text(ticket_export.report.public_number, format_name="CSV")
    )
    _, kwargs = bot.send_document.await_args
    assert kwargs["caption"] == "Отчёт по заявке HD-AAAA1111"
    assert kwargs["document"].filename == "ticket-report-hd-aaaa1111.csv"


def callback_answer_mock(callback: CallbackQuery) -> AsyncMock:
    return cast(AsyncMock, callback.answer)


def message_edit_text_mock(callback: CallbackQuery) -> AsyncMock:
    assert isinstance(callback.message, Message)
    return cast(AsyncMock, callback.message.edit_text)
