from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

from bot.handlers.user.intake import handle_client_intake_message
from bot.handlers.user.intake_draft import (
    PendingClientIntakeDraft,
    serialize_pending_client_intake_draft,
)
from bot.texts.client import (
    build_ticket_created_text,
    build_ticket_created_with_missing_follow_up_text,
)
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketAttachmentKind


async def test_intake_message_creates_ticket_with_selected_category(
    backend_client_factory_builder,
    message_harness_builder,
    ticket_summary_builder,
    ticket_details_builder,
    publisher: SimpleNamespace,
) -> None:
    ticket_public_id = uuid4()
    harness = message_harness_builder(text="Не получается войти")
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"category_id": 2}),
        clear=AsyncMock(),
    )
    ticket = ticket_summary_builder(ticket_public_id)
    ticket_details = ticket_details_builder(
        public_id=ticket_public_id,
        subject="Не получается войти",
        category_id=2,
        category_title="Другая тема",
    )
    service = SimpleNamespace(
        create_ticket_from_client_intake=AsyncMock(return_value=ticket),
        create_ticket_from_client_message=AsyncMock(return_value=ticket),
        get_ticket_details=AsyncMock(return_value=ticket_details),
    )

    await handle_client_intake_message(
        message=harness.message,
        state=state,
        bot=Mock(),
        helpdesk_backend_client_factory=backend_client_factory_builder(service),
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
    harness.answer.assert_awaited_once_with(
        build_ticket_created_text(ticket.public_number),
        reply_markup=ANY,
    )


async def test_intake_with_initial_attachment_keeps_first_media_and_saves_follow_up_text(
    backend_client_factory_builder,
    message_harness_builder,
    ticket_summary_builder,
    ticket_details_builder,
    publisher: SimpleNamespace,
) -> None:
    ticket_public_id = uuid4()
    attachment = TicketAttachmentDetails(
        kind=TicketAttachmentKind.PHOTO,
        telegram_file_id="photo-1",
        telegram_file_unique_id="photo-unique-1",
        filename=None,
        mime_type="image/jpeg",
        storage_path="photo/photo-unique-1.jpg",
    )
    harness = message_harness_builder(text="На фото видно ошибку", message_id=22)
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
    ticket = ticket_summary_builder(ticket_public_id)
    ticket_details = ticket_details_builder(
        public_id=ticket_public_id,
        subject="Фото",
        category_id=2,
        category_title="Доступ и вход",
    )
    service = SimpleNamespace(
        create_ticket_from_client_intake=AsyncMock(return_value=ticket),
        create_ticket_from_client_message=AsyncMock(return_value=ticket),
        get_ticket_details=AsyncMock(return_value=ticket_details),
    )

    await handle_client_intake_message(
        message=harness.message,
        state=state,
        bot=Mock(),
        helpdesk_backend_client_factory=backend_client_factory_builder(service),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        chat_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        operator_active_ticket_store=SimpleNamespace(
            get_active_ticket=AsyncMock(return_value=None)
        ),
        ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
        ticket_stream_publisher=publisher,
    )

    intake_command = service.create_ticket_from_client_intake.await_args.args[0]
    assert intake_command.telegram_message_id == 15
    assert intake_command.text is None
    assert intake_command.attachment == attachment

    follow_up_command = service.create_ticket_from_client_message.await_args.args[0]
    assert follow_up_command.telegram_message_id == 22
    assert follow_up_command.text == "На фото видно ошибку"
    assert follow_up_command.attachment is None

    publisher.publish_new_ticket.assert_awaited_once_with(
        ticket_id=str(ticket_public_id),
        client_chat_id=2002,
        subject="Фото",
    )
    harness.answer.assert_awaited_once_with(
        build_ticket_created_text(ticket.public_number),
        reply_markup=ANY,
    )


async def test_intake_preserves_first_media_when_follow_up_text_save_fails(
    backend_client_factory_builder,
    message_harness_builder,
    ticket_summary_builder,
    ticket_details_builder,
    publisher: SimpleNamespace,
) -> None:
    ticket_public_id = uuid4()
    attachment = TicketAttachmentDetails(
        kind=TicketAttachmentKind.DOCUMENT,
        telegram_file_id="file-1",
        telegram_file_unique_id="unique-1",
        filename="issue.txt",
        mime_type="text/plain",
        storage_path="document/unique-1.txt",
    )
    harness = message_harness_builder(text="Описание после выбора темы", message_id=22)
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
    ticket = ticket_summary_builder(ticket_public_id)
    ticket_details = ticket_details_builder(
        public_id=ticket_public_id,
        subject="Файл · issue.txt",
        category_id=3,
        category_title="Другая тема",
    )
    service = SimpleNamespace(
        create_ticket_from_client_intake=AsyncMock(return_value=ticket),
        create_ticket_from_client_message=AsyncMock(side_effect=RuntimeError("backend down")),
        get_ticket_details=AsyncMock(return_value=ticket_details),
    )

    await handle_client_intake_message(
        message=harness.message,
        state=state,
        bot=Mock(),
        helpdesk_backend_client_factory=backend_client_factory_builder(service),
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
    publisher.publish_new_ticket.assert_awaited_once_with(
        ticket_id=str(ticket_public_id),
        client_chat_id=2002,
        subject="Файл · issue.txt",
    )
    harness.answer.assert_awaited_once_with(
        build_ticket_created_with_missing_follow_up_text(ticket.public_number),
        reply_markup=ANY,
    )
