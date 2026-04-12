from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

from aiogram.types import CallbackQuery, Chat, Message, User

from application.ai.summaries import TicketCategoryPrediction
from application.use_cases.tickets.summaries import (
    TicketCategorySummary,
    TicketDetailsSummary,
    TicketSummary,
)
from backend.grpc.contracts import HelpdeskBackendClient, HelpdeskBackendClientFactory
from bot.handlers.user.client import handle_client_text
from bot.handlers.user.intake import (
    handle_client_intake_category_pick,
    handle_client_intake_message,
)
from bot.handlers.user.intake_draft import (
    PendingClientIntakeDraft,
    serialize_pending_client_intake_draft,
)
from bot.handlers.user.states import UserIntakeStates
from bot.texts.categories import INTAKE_CATEGORY_PROMPT_TEXT
from bot.texts.client import build_ticket_created_text, build_ticket_message_added_text
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketAttachmentKind, TicketStatus


def build_helpdesk_backend_client_factory(service: object) -> HelpdeskBackendClientFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[HelpdeskBackendClient]:
        yield cast(HelpdeskBackendClient, service)

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
    state = SimpleNamespace(set_state=AsyncMock(), set_data=AsyncMock())
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
        predict_ticket_category=AsyncMock(return_value=TicketCategoryPrediction(available=False)),
    )

    await handle_client_text(
        message=message,
        state=state,
        bot=Mock(),
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
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
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        chat_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        operator_active_ticket_store=SimpleNamespace(
            get_active_ticket=AsyncMock(return_value=None)
        ),
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
        create_ticket_from_client_message=AsyncMock(return_value=ticket),
        get_ticket_details=AsyncMock(return_value=ticket_details),
    )
    publisher = SimpleNamespace(publish_new_ticket=AsyncMock())

    await handle_client_intake_message(
        message=message,
        state=state,
        bot=Mock(),
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        chat_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        operator_active_ticket_store=SimpleNamespace(
            get_active_ticket=AsyncMock(return_value=None)
        ),
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


async def test_intake_with_initial_attachment_keeps_first_media_and_saves_follow_up_text() -> None:
    ticket_public_id = uuid4()
    attachment = TicketAttachmentDetails(
        kind=TicketAttachmentKind.PHOTO,
        telegram_file_id="photo-1",
        telegram_file_unique_id="photo-unique-1",
        filename=None,
        mime_type="image/jpeg",
        storage_path="photo/photo-unique-1.jpg",
    )
    message = build_message(text="На фото видно ошибку", message_id=22)
    draft = PendingClientIntakeDraft(
        client_chat_id=2002,
        telegram_message_id=15,
        text=None,
        attachment=attachment,
    )
    state = SimpleNamespace(
        get_data=AsyncMock(
            return_value={
                "category_id": 2,
                "category_title": "Доступ и вход",
                "draft": serialize_pending_client_intake_draft(draft),
            }
        ),
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
        subject="Обращение клиента",
        assigned_operator_id=None,
        assigned_operator_name=None,
        assigned_operator_telegram_user_id=None,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
        category_id=2,
        category_title="Доступ и вход",
    )
    service = SimpleNamespace(
        create_ticket_from_client_intake=AsyncMock(return_value=ticket),
        create_ticket_from_client_message=AsyncMock(return_value=ticket),
        get_ticket_details=AsyncMock(return_value=ticket_details),
    )
    publisher = SimpleNamespace(publish_new_ticket=AsyncMock())

    await handle_client_intake_message(
        message=message,
        state=state,
        bot=Mock(),
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        chat_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        operator_active_ticket_store=SimpleNamespace(
            get_active_ticket=AsyncMock(return_value=None)
        ),
        ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
        ticket_stream_publisher=publisher,
    )

    state.clear.assert_awaited_once_with()
    service.create_ticket_from_client_intake.assert_awaited_once()
    intake_command = service.create_ticket_from_client_intake.await_args.args[0]
    assert intake_command.telegram_message_id == 15
    assert intake_command.text is None
    assert intake_command.attachment == attachment

    service.create_ticket_from_client_message.assert_awaited_once()
    follow_up_command = service.create_ticket_from_client_message.await_args.args[0]
    assert follow_up_command.telegram_message_id == 22
    assert follow_up_command.text == "На фото видно ошибку"
    assert follow_up_command.attachment is None

    publisher.publish_new_ticket.assert_awaited_once_with(
        ticket_id=str(ticket_public_id),
        client_chat_id=2002,
        subject="Обращение клиента",
    )
    cast(AsyncMock, message.answer).assert_awaited_once_with(
        build_ticket_created_text(ticket.public_number),
        reply_markup=ANY,
    )


async def test_category_pick_creates_ticket_immediately_when_first_text_is_already_saved() -> None:
    ticket_public_id = uuid4()
    callback_message = build_message(text="stub", message_id=77)
    object.__setattr__(callback_message, "edit_text", AsyncMock())
    callback = CallbackQuery.model_construct(
        id="pick-id",
        from_user=User.model_construct(id=2002, is_bot=False, first_name="Client"),
        chat_instance="chat-instance",
        message=callback_message,
        data="client_intake:pick:2",
    )
    object.__setattr__(callback, "answer", AsyncMock())
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
        subject="Помогите с доступом",
        assigned_operator_id=None,
        assigned_operator_name=None,
        assigned_operator_telegram_user_id=None,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
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
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        operator_active_ticket_store=SimpleNamespace(
            get_active_ticket=AsyncMock(return_value=None)
        ),
        ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
        ticket_stream_publisher=SimpleNamespace(publish_new_ticket=AsyncMock()),
    )

    state.clear.assert_awaited_once_with()
    service.create_ticket_from_client_intake.assert_awaited_once()
    command = service.create_ticket_from_client_intake.await_args.args[0]
    assert command.text == "Помогите с доступом"
    assert command.category_id == 2


async def test_intake_keeps_initial_attachment_until_text_arrives() -> None:
    ticket_public_id = uuid4()
    attachment = TicketAttachmentDetails(
        kind=TicketAttachmentKind.DOCUMENT,
        telegram_file_id="file-1",
        telegram_file_unique_id="unique-1",
        filename="issue.txt",
        mime_type="text/plain",
        storage_path="document/unique-1.txt",
    )
    message = build_message(text="Описание после выбора темы")
    state = SimpleNamespace(
        get_data=AsyncMock(
            return_value={
                "category_id": 3,
                "category_title": "Другая тема",
                "draft": serialize_pending_client_intake_draft(
                    PendingClientIntakeDraft(
                        client_chat_id=2002,
                        telegram_message_id=15,
                        text=None,
                        attachment=attachment,
                    )
                ),
            }
        ),
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
        subject="Описание после выбора темы",
        assigned_operator_id=None,
        assigned_operator_name=None,
        assigned_operator_telegram_user_id=None,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
        category_id=3,
        category_title="Другая тема",
    )
    service = SimpleNamespace(
        create_ticket_from_client_intake=AsyncMock(return_value=ticket),
        create_ticket_from_client_message=AsyncMock(return_value=ticket),
        get_ticket_details=AsyncMock(return_value=ticket_details),
    )
    publisher = SimpleNamespace(publish_new_ticket=AsyncMock())

    await handle_client_intake_message(
        message=message,
        state=state,
        bot=Mock(),
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        chat_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        operator_active_ticket_store=SimpleNamespace(
            get_active_ticket=AsyncMock(return_value=None)
        ),
        ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
        ticket_stream_publisher=publisher,
    )

    intake_command = service.create_ticket_from_client_intake.await_args.args[0]
    assert intake_command.text is None
    assert intake_command.attachment == attachment

    follow_up_command = service.create_ticket_from_client_message.await_args.args[0]
    assert follow_up_command.text == "Описание после выбора темы"
    assert follow_up_command.attachment is None
