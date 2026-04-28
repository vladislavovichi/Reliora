from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Protocol
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

from aiogram.types import Message

from application.use_cases.tickets.summaries import TicketDetailsSummary, TicketSummary
from bot.handlers.user.intake import handle_client_intake_message
from bot.handlers.user.intake_context import ClientIntakeContext
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


class MessageHarness(Protocol):
    message: Message
    answer: AsyncMock


class MessageHarnessBuilder(Protocol):
    def __call__(
        self,
        *,
        text: str,
        chat_id: int = 2002,
        message_id: int = 15,
    ) -> MessageHarness: ...


class TicketDetailsBuilder(Protocol):
    def __call__(
        self,
        *,
        public_id: object,
        subject: str,
        category_id: int,
        category_title: str,
    ) -> TicketDetailsSummary: ...


TicketSummaryBuilder = Callable[[object], TicketSummary]
ClientIntakeContextBuilder = Callable[[object, SimpleNamespace | None], ClientIntakeContext]


async def test_intake_message_creates_ticket_with_selected_category(
    message_harness_builder: MessageHarnessBuilder,
    ticket_summary_builder: TicketSummaryBuilder,
    ticket_details_builder: TicketDetailsBuilder,
    client_intake_context_builder: ClientIntakeContextBuilder,
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
        client_intake_context=client_intake_context_builder(service, publisher),
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
    message_harness_builder: MessageHarnessBuilder,
    ticket_summary_builder: TicketSummaryBuilder,
    ticket_details_builder: TicketDetailsBuilder,
    client_intake_context_builder: ClientIntakeContextBuilder,
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
        client_intake_context=client_intake_context_builder(service, publisher),
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
    message_harness_builder: MessageHarnessBuilder,
    ticket_summary_builder: TicketSummaryBuilder,
    ticket_details_builder: TicketDetailsBuilder,
    client_intake_context_builder: ClientIntakeContextBuilder,
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
        client_intake_context=client_intake_context_builder(service, publisher),
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


async def test_intake_ticket_creation_still_replies_when_stream_publish_fails(
    message_harness_builder: MessageHarnessBuilder,
    ticket_summary_builder: TicketSummaryBuilder,
    ticket_details_builder: TicketDetailsBuilder,
    client_intake_context_builder: ClientIntakeContextBuilder,
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
        category_title="Доступ и вход",
    )
    service = SimpleNamespace(
        create_ticket_from_client_intake=AsyncMock(return_value=ticket),
        get_ticket_details=AsyncMock(return_value=ticket_details),
    )
    publisher.publish_new_ticket.side_effect = RuntimeError("redis unavailable")

    await handle_client_intake_message(
        message=harness.message,
        state=state,
        bot=Mock(),
        client_intake_context=client_intake_context_builder(service, publisher),
    )

    service.create_ticket_from_client_intake.assert_awaited_once()
    publisher.publish_new_ticket.assert_awaited_once()
    harness.answer.assert_awaited_once_with(
        build_ticket_created_text(ticket.public_number),
        reply_markup=ANY,
    )
