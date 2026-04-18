from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Protocol
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from aiogram.types import CallbackQuery, Message

from application.use_cases.tickets.summaries import (
    TicketCategorySummary,
    TicketDetailsSummary,
    TicketSummary,
)
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.handlers.user.intake import handle_client_intake_category_pick
from bot.handlers.user.intake_draft import (
    PendingClientIntakeDraft,
    serialize_pending_client_intake_draft,
)
from bot.handlers.user.states import UserIntakeStates
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketAttachmentKind


class MessageHarness(Protocol):
    message: Message


class MessageHarnessBuilder(Protocol):
    def __call__(
        self,
        *,
        text: str,
        chat_id: int = 2002,
        message_id: int = 15,
    ) -> MessageHarness: ...


class CallbackBuilder(Protocol):
    def __call__(
        self,
        *,
        message: Message,
        data: str,
        user_id: int = 2002,
    ) -> tuple[CallbackQuery, AsyncMock]: ...


class TicketDetailsBuilder(Protocol):
    def __call__(
        self,
        *,
        public_id: object,
        subject: str,
        category_id: int,
        category_title: str,
    ) -> TicketDetailsSummary: ...


BackendClientFactoryBuilder = Callable[[object], HelpdeskBackendClientFactory]
TicketSummaryBuilder = Callable[[object], TicketSummary]


async def test_category_pick_creates_ticket_immediately_when_first_text_is_already_saved(
    backend_client_factory_builder: BackendClientFactoryBuilder,
    callback_builder: CallbackBuilder,
    message_harness_builder: MessageHarnessBuilder,
    ticket_summary_builder: TicketSummaryBuilder,
    ticket_details_builder: TicketDetailsBuilder,
) -> None:
    ticket_public_id = uuid4()
    harness = message_harness_builder(text="stub", message_id=77)
    callback, callback_answer = callback_builder(
        message=harness.message,
        data="client_intake:pick:2",
    )
    draft = PendingClientIntakeDraft(
        client_chat_id=2002,
        telegram_message_id=15,
        text="Помогите с доступом",
        attachment=None,
    )
    state = SimpleNamespace(
        get_state=AsyncMock(return_value=UserIntakeStates.choosing_category.state),
        get_data=AsyncMock(return_value={"draft": serialize_pending_client_intake_draft(draft)}),
        clear=AsyncMock(),
    )
    ticket = ticket_summary_builder(ticket_public_id)
    ticket_details = ticket_details_builder(
        public_id=ticket_public_id,
        subject="Помогите с доступом",
        category_id=2,
        category_title="Доступ и вход",
    )
    service = SimpleNamespace(
        list_client_ticket_categories=AsyncMock(
            return_value=(
                TicketCategorySummary(
                    id=2,
                    code="access",
                    title="Доступ и вход",
                    is_active=True,
                    sort_order=10,
                ),
            )
        ),
        create_ticket_from_client_intake=AsyncMock(return_value=ticket),
        get_ticket_details=AsyncMock(return_value=ticket_details),
    )

    await handle_client_intake_category_pick(
        callback=callback,
        callback_data=SimpleNamespace(category_id=2),
        state=state,
        bot=Mock(),
        helpdesk_backend_client_factory=backend_client_factory_builder(service),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        operator_active_ticket_store=SimpleNamespace(
            get_active_ticket=AsyncMock(return_value=None)
        ),
        ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
        ticket_stream_publisher=SimpleNamespace(publish_new_ticket=AsyncMock()),
    )

    callback_answer.assert_awaited_once_with()
    state.clear.assert_awaited_once_with()
    command = service.create_ticket_from_client_intake.await_args.args[0]
    assert command.text == "Помогите с доступом"
    assert command.category_id == 2


async def test_category_pick_with_initial_photo_creates_ticket_immediately(
    backend_client_factory_builder: BackendClientFactoryBuilder,
    callback_builder: CallbackBuilder,
    message_harness_builder: MessageHarnessBuilder,
    ticket_summary_builder: TicketSummaryBuilder,
    ticket_details_builder: TicketDetailsBuilder,
) -> None:
    ticket_public_id = uuid4()
    harness = message_harness_builder(text="stub", message_id=77)
    callback, callback_answer = callback_builder(
        message=harness.message,
        data="client_intake:pick:2",
    )
    attachment = TicketAttachmentDetails(
        kind=TicketAttachmentKind.PHOTO,
        telegram_file_id="photo-1",
        telegram_file_unique_id="photo-unique-1",
        filename=None,
        mime_type="image/jpeg",
        storage_path="photo/photo-unique-1.jpg",
    )
    draft = PendingClientIntakeDraft(
        client_chat_id=2002,
        telegram_message_id=15,
        text=None,
        attachment=attachment,
    )
    state = SimpleNamespace(
        get_state=AsyncMock(return_value=UserIntakeStates.choosing_category.state),
        get_data=AsyncMock(return_value={"draft": serialize_pending_client_intake_draft(draft)}),
        clear=AsyncMock(),
    )
    ticket = ticket_summary_builder(ticket_public_id)
    ticket_details = ticket_details_builder(
        public_id=ticket_public_id,
        subject="Фото",
        category_id=2,
        category_title="Доступ и вход",
    )
    service = SimpleNamespace(
        list_client_ticket_categories=AsyncMock(
            return_value=(
                TicketCategorySummary(
                    id=2,
                    code="access",
                    title="Доступ и вход",
                    is_active=True,
                    sort_order=10,
                ),
            )
        ),
        create_ticket_from_client_intake=AsyncMock(return_value=ticket),
        get_ticket_details=AsyncMock(return_value=ticket_details),
    )

    await handle_client_intake_category_pick(
        callback=callback,
        callback_data=SimpleNamespace(category_id=2),
        state=state,
        bot=Mock(),
        helpdesk_backend_client_factory=backend_client_factory_builder(service),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        operator_active_ticket_store=SimpleNamespace(
            get_active_ticket=AsyncMock(return_value=None)
        ),
        ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
        ticket_stream_publisher=SimpleNamespace(publish_new_ticket=AsyncMock()),
    )

    callback_answer.assert_awaited_once_with()
    state.clear.assert_awaited_once_with()
    command = service.create_ticket_from_client_intake.await_args.args[0]
    assert command.text is None
    assert command.attachment == attachment
    assert command.category_id == 2
