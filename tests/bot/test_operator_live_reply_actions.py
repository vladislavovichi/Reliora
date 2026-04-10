from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

from aiogram.types import Chat, Message, User

from application.use_cases.tickets.summaries import (
    OperatorReplyResult,
    TicketDetailsSummary,
    TicketSummary,
)
from backend.grpc.contracts import HelpdeskBackendClient, HelpdeskBackendClientFactory
from bot.handlers.operator.workflow_reply import _handle_operator_message
from bot.texts.operator import build_reply_sent_text
from domain.enums.tickets import TicketStatus


def _build_helpdesk_backend_client_factory(service: object) -> HelpdeskBackendClientFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[HelpdeskBackendClient]:
        yield cast(HelpdeskBackendClient, service)

    return provide


def _build_message() -> Message:
    message = Message.model_construct(
        message_id=20,
        date=datetime.now(UTC),
        chat=Chat.model_construct(id=3001, type="private"),
        from_user=User.model_construct(id=1001, is_bot=False, first_name="Operator"),
        text="Держу вас в курсе",
    )
    object.__setattr__(message, "answer", AsyncMock())
    return message


async def test_operator_reply_refreshes_action_surface_after_successful_live_message() -> None:
    ticket_public_id = uuid4()
    message = _build_message()
    ticket_details = TicketDetailsSummary(
        public_id=ticket_public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        status=TicketStatus.ASSIGNED,
        priority="normal",
        subject="Нужна помощь",
        assigned_operator_id=7,
        assigned_operator_name="Иван Петров",
        assigned_operator_telegram_user_id=1001,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
    )
    reply_result = OperatorReplyResult(
        ticket=TicketSummary(
            public_id=ticket_public_id,
            public_number="HD-AAAA1111",
            status=TicketStatus.ASSIGNED,
            created=False,
        ),
        client_chat_id=2002,
    )
    service = SimpleNamespace(
        get_ticket_details=AsyncMock(return_value=ticket_details),
        reply_to_ticket_as_operator=AsyncMock(return_value=reply_result),
    )
    bot = Mock()
    bot.send_message = AsyncMock()
    lock = SimpleNamespace(acquire=AsyncMock(return_value=True), release=AsyncMock())

    await _handle_operator_message(
        message=message,
        bot=bot,
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        operator_presence=SimpleNamespace(touch=AsyncMock()),
        operator_active_ticket_store=SimpleNamespace(
            set_active_ticket=AsyncMock(),
            clear_if_matches=AsyncMock(),
            get_active_ticket=AsyncMock(return_value=str(ticket_public_id)),
        ),
        ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
        ticket_lock_manager=SimpleNamespace(for_ticket=Mock(return_value=lock)),
        explicit_ticket_public_id=ticket_public_id,
    )

    cast(AsyncMock, message.answer).assert_awaited_once_with(
        build_reply_sent_text(reply_result.ticket.public_number),
        reply_markup=ANY,
    )
