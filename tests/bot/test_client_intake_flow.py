from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

from aiogram.types import Chat, Message, User

from application.services.helpdesk.service import HelpdeskService, HelpdeskServiceFactory
from application.use_cases.tickets.summaries import (
    TicketCategorySummary,
    TicketDetailsSummary,
    TicketSummary,
)
from bot.handlers.user.client import handle_client_text
from bot.handlers.user.intake import handle_client_intake_message
from bot.handlers.user.states import UserIntakeStates
from bot.texts.categories import INTAKE_CATEGORY_PROMPT_TEXT
from bot.texts.client import build_ticket_created_text, build_ticket_message_added_text
from domain.enums.tickets import TicketStatus


def build_helpdesk_service_factory(service: object) -> HelpdeskServiceFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[HelpdeskService]:
        yield cast(HelpdeskService, service)

    return provide


def build_message(*, text: str, chat_id: int = 2002, message_id: int = 15) -> Message:
    message = Message.model_construct(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat.model_construct(id=chat_id, type="private"),
        from_user=User.model_construct(id=chat_id, is_bot=False, first_name="Client"),
        text=text,
    )
    object.__setattr__(message, "answer", AsyncMock())
    return message


async def test_client_first_message_without_active_ticket_starts_intake_flow() -> None:
    message = build_message(text="Помогите с доступом")
    state = SimpleNamespace(set_state=AsyncMock())
    service = SimpleNamespace(
        get_client_active_ticket=AsyncMock(return_value=None),
        list_client_ticket_categories=AsyncMock(
            return_value=[
                TicketCategorySummary(
                    id=1,
                    code="access",
                    title="Доступ и вход",
                    is_active=True,
                    sort_order=10,
                )
            ]
        ),
    )

    await handle_client_text(
        message=message,
        state=state,
        bot=Mock(),
        helpdesk_service_factory=build_helpdesk_service_factory(service),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        chat_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        operator_active_ticket_store=SimpleNamespace(get_active_ticket=AsyncMock()),
        ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
        ticket_stream_publisher=SimpleNamespace(publish_new_ticket=AsyncMock()),
    )

    state.set_state.assert_awaited_once_with(UserIntakeStates.choosing_category)
    cast(AsyncMock, message.answer).assert_awaited_once_with(
        INTAKE_CATEGORY_PROMPT_TEXT,
        reply_markup=ANY,
    )


async def test_client_message_with_active_ticket_keeps_live_dialogue_path() -> None:
    ticket_public_id = uuid4()
    message = build_message(text="Есть обновления?")
    state = SimpleNamespace(set_state=AsyncMock())
    ticket = TicketSummary(
        public_id=ticket_public_id,
        public_number="HD-AAAA1111",
        status=TicketStatus.ASSIGNED,
        created=False,
    )
    ticket_details = TicketDetailsSummary(
        public_id=ticket_public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        status=TicketStatus.ASSIGNED,
        priority="normal",
        subject="Нужна помощь",
        assigned_operator_id=None,
        assigned_operator_name=None,
        assigned_operator_telegram_user_id=None,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
    )
    service = SimpleNamespace(
        get_client_active_ticket=AsyncMock(return_value=ticket),
        create_ticket_from_client_message=AsyncMock(return_value=ticket),
        get_ticket_details=AsyncMock(return_value=ticket_details),
    )

    await handle_client_text(
        message=message,
        state=state,
        bot=Mock(),
        helpdesk_service_factory=build_helpdesk_service_factory(service),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        chat_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        operator_active_ticket_store=SimpleNamespace(get_active_ticket=AsyncMock(return_value=None)),
        ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
        ticket_stream_publisher=SimpleNamespace(publish_new_ticket=AsyncMock()),
    )

    service.create_ticket_from_client_message.assert_awaited_once()
    state.set_state.assert_not_called()
    cast(AsyncMock, message.answer).assert_awaited_once_with(
        build_ticket_message_added_text(ticket.public_number, operator_connected=False),
        reply_markup=ANY,
    )


async def test_intake_message_creates_ticket_with_selected_category() -> None:
    ticket_public_id = uuid4()
    message = build_message(text="Не получается войти")
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"category_id": 2}),
        clear=AsyncMock(),
    )
    ticket = TicketSummary(
        public_id=ticket_public_id,
        public_number="HD-AAAA1111",
        status=TicketStatus.QUEUED,
        created=True,
    )
    ticket_details = TicketDetailsSummary(
        public_id=ticket_public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        status=TicketStatus.QUEUED,
        priority="normal",
        subject="Не получается войти",
        assigned_operator_id=None,
        assigned_operator_name=None,
        assigned_operator_telegram_user_id=None,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
        category_id=2,
        category_title="Другая тема",
    )
    service = SimpleNamespace(
        create_ticket_from_client_intake=AsyncMock(return_value=ticket),
        get_ticket_details=AsyncMock(return_value=ticket_details),
    )
    publisher = SimpleNamespace(publish_new_ticket=AsyncMock())

    await handle_client_intake_message(
        message=message,
        state=state,
        bot=Mock(),
        helpdesk_service_factory=build_helpdesk_service_factory(service),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        chat_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        operator_active_ticket_store=SimpleNamespace(get_active_ticket=AsyncMock(return_value=None)),
        ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
        ticket_stream_publisher=publisher,
    )

    state.clear.assert_awaited_once_with()
    service.create_ticket_from_client_intake.assert_awaited_once()
    publisher.publish_new_ticket.assert_awaited_once_with(
        ticket_id=str(ticket_public_id),
        client_chat_id=2002,
        subject="Не получается войти",
    )
    cast(AsyncMock, message.answer).assert_awaited_once_with(
        build_ticket_created_text(ticket.public_number),
        reply_markup=ANY,
    )
