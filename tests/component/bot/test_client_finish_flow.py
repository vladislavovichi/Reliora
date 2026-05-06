from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

from aiogram.exceptions import TelegramBadRequest

from application.contracts.actors import RequestActor
from application.use_cases.tickets.summaries import TicketDetailsSummary, TicketSummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.handlers.user.client import (
    handle_finish_ticket_confirm,
    handle_finish_ticket_prompt,
)
from bot.keyboards.inline.feedback import build_ticket_feedback_rating_markup
from bot.texts.client import (
    FINISH_TICKET_STALE_TEXT,
    build_ticket_already_closed_text,
)
from bot.texts.feedback import build_ticket_closed_with_feedback_text
from domain.enums.tickets import TicketStatus
from domain.tickets import InvalidTicketTransitionError
from tests.support.aiogram import CallbackHarness, build_callback_harness
from tests.support.backend import FakeHelpdeskBackendClient, build_backend_client_factory


class FinishTicketBackendClient(FakeHelpdeskBackendClient):
    def __init__(
        self,
        *,
        ticket_details: TicketDetailsSummary | Sequence[TicketDetailsSummary | None] | None = None,
        close_ticket_result: TicketSummary | None = None,
        close_ticket_error: Exception | None = None,
    ) -> None:
        self._ticket_details = (
            list(ticket_details)
            if isinstance(ticket_details, Sequence) and not isinstance(ticket_details, str)
            else ticket_details
        )
        self._close_ticket_result = close_ticket_result
        self._close_ticket_error = close_ticket_error
        self.get_ticket_details_mock = AsyncMock()
        self.close_ticket_mock = AsyncMock()

    async def get_ticket_details(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketDetailsSummary | None:
        await self.get_ticket_details_mock(
            ticket_public_id=ticket_public_id,
            actor=actor,
        )
        if isinstance(self._ticket_details, list):
            return self._ticket_details.pop(0)
        return self._ticket_details

    async def close_ticket(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        await self.close_ticket_mock(ticket_public_id=ticket_public_id, actor=actor)
        if self._close_ticket_error is not None:
            raise self._close_ticket_error
        return self._close_ticket_result


def build_helpdesk_backend_client_factory(
    service: FakeHelpdeskBackendClient,
) -> HelpdeskBackendClientFactory:
    return build_backend_client_factory(service)


def build_callback(*, ticket_public_id: str) -> CallbackHarness:
    return build_callback_harness(
        user_id=2002,
        data=f"client_ticket:finish:{ticket_public_id}",
        with_edit_reply_markup=True,
    )


def build_ticket_details(*, public_id: UUID, status: TicketStatus) -> TicketDetailsSummary:
    return TicketDetailsSummary(
        public_id=public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        status=status,
        priority="normal",
        subject="Нужна помощь",
        assigned_operator_id=7,
        assigned_operator_name="Иван Петров",
        assigned_operator_telegram_user_id=1001,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
        tags=(),
        last_message_text="Добрый день",
        last_message_sender_type=None,
        message_history=(),
    )


async def test_finish_ticket_prompt_uses_domain_stale_text_for_missing_ticket() -> None:
    ticket_public_id = str(uuid4())
    callback = build_callback(ticket_public_id=ticket_public_id)
    service = FinishTicketBackendClient(ticket_details=None)
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))

    await handle_finish_ticket_prompt(
        callback=callback.callback,
        callback_data=SimpleNamespace(ticket_public_id=ticket_public_id),
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
    )

    callback.answer.assert_awaited_once_with(
        FINISH_TICKET_STALE_TEXT,
        show_alert=True,
    )
    assert callback.message.edit_reply_markup is not None
    callback.message.edit_reply_markup.assert_not_awaited()


async def test_finish_ticket_confirm_closes_ticket_and_cleans_runtime_state() -> None:
    ticket_public_id = uuid4()
    callback = build_callback(ticket_public_id=str(ticket_public_id))
    ticket_details = build_ticket_details(public_id=ticket_public_id, status=TicketStatus.ASSIGNED)
    closed_ticket = TicketSummary(
        public_id=ticket_public_id,
        public_number=ticket_details.public_number,
        status=TicketStatus.CLOSED,
    )

    service = FinishTicketBackendClient(
        ticket_details=ticket_details,
        close_ticket_result=closed_ticket,
    )
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    operator_active_ticket_store = SimpleNamespace(clear_if_matches=AsyncMock())
    ticket_live_session_store = SimpleNamespace(delete_session=AsyncMock())
    lock = SimpleNamespace(acquire=AsyncMock(return_value=True), release=AsyncMock())
    ticket_lock_manager = SimpleNamespace(for_ticket=Mock(return_value=lock))
    bot = Mock()
    bot.send_message = AsyncMock()

    await handle_finish_ticket_confirm(
        callback=callback.callback,
        callback_data=SimpleNamespace(ticket_public_id=str(ticket_public_id)),
        bot=bot,
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
        operator_active_ticket_store=operator_active_ticket_store,
        ticket_live_session_store=ticket_live_session_store,
        ticket_lock_manager=ticket_lock_manager,
    )

    ticket_live_session_store.delete_session.assert_awaited_once_with(
        ticket_public_id=str(ticket_public_id)
    )
    operator_active_ticket_store.clear_if_matches.assert_awaited_once_with(
        operator_id=ticket_details.assigned_operator_telegram_user_id,
        ticket_public_id=str(ticket_public_id),
    )
    bot.send_message.assert_awaited_once()
    assert callback.message.edit_reply_markup is not None
    callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    callback.message.answer.assert_awaited_once_with(
        build_ticket_closed_with_feedback_text(ticket_details.public_number),
        reply_markup=build_ticket_feedback_rating_markup(ticket_public_id=ticket_public_id),
    )
    callback.answer.assert_awaited_once_with()
    lock.release.assert_awaited_once_with()


async def test_finish_ticket_confirm_returns_closed_message_after_race() -> None:
    ticket_public_id = uuid4()
    callback = build_callback(ticket_public_id=str(ticket_public_id))
    open_ticket_details = build_ticket_details(
        public_id=ticket_public_id,
        status=TicketStatus.ASSIGNED,
    )
    closed_ticket_details = build_ticket_details(
        public_id=ticket_public_id,
        status=TicketStatus.CLOSED,
    )

    service = FinishTicketBackendClient(
        ticket_details=[open_ticket_details, closed_ticket_details],
        close_ticket_error=InvalidTicketTransitionError("already closed"),
    )
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    operator_active_ticket_store = SimpleNamespace(clear_if_matches=AsyncMock())
    ticket_live_session_store = SimpleNamespace(delete_session=AsyncMock())
    lock = SimpleNamespace(acquire=AsyncMock(return_value=True), release=AsyncMock())
    ticket_lock_manager = SimpleNamespace(for_ticket=Mock(return_value=lock))
    bot = Mock()
    bot.send_message = AsyncMock()

    await handle_finish_ticket_confirm(
        callback=callback.callback,
        callback_data=SimpleNamespace(ticket_public_id=str(ticket_public_id)),
        bot=bot,
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
        operator_active_ticket_store=operator_active_ticket_store,
        ticket_live_session_store=ticket_live_session_store,
        ticket_lock_manager=ticket_lock_manager,
    )

    callback.answer.assert_awaited_once_with(
        build_ticket_already_closed_text(closed_ticket_details.public_number),
        show_alert=True,
    )
    ticket_live_session_store.delete_session.assert_not_called()
    operator_active_ticket_store.clear_if_matches.assert_not_called()
    callback.message.answer.assert_not_awaited()
    lock.release.assert_awaited_once_with()


async def test_finish_ticket_prompt_uses_domain_stale_text_when_markup_is_outdated() -> None:
    ticket_public_id = uuid4()
    callback = build_callback(ticket_public_id=str(ticket_public_id))
    ticket_details = build_ticket_details(public_id=ticket_public_id, status=TicketStatus.ASSIGNED)
    service = FinishTicketBackendClient(ticket_details=ticket_details)
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    assert callback.message.edit_reply_markup is not None
    callback.message.edit_reply_markup.side_effect = TelegramBadRequest(
        method=Mock(),
        message="message is not modified",
    )

    await handle_finish_ticket_prompt(
        callback=callback.callback,
        callback_data=SimpleNamespace(ticket_public_id=str(ticket_public_id)),
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
    )

    callback.answer.assert_awaited_once_with(
        FINISH_TICKET_STALE_TEXT,
        show_alert=True,
    )
