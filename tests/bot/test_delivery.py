from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from pytest import MonkeyPatch

from application.use_cases.tickets.summaries import TicketAttachmentSummary
from bot.delivery import (
    deliver_client_message_to_operator,
    deliver_document_to_chat,
    deliver_operator_reply_to_client,
    deliver_ticket_closed_to_client,
    deliver_ticket_closed_to_operator,
    send_document_with_retry,
    send_message_with_retry,
)
from bot.keyboards.inline.feedback import build_ticket_feedback_rating_markup
from bot.texts.feedback import build_ticket_closed_with_feedback_text
from domain.enums.tickets import TicketAttachmentKind


async def test_send_message_with_retry_recovers_from_network_error(
    monkeypatch: MonkeyPatch,
) -> None:
    bot = Mock()
    bot.send_message = AsyncMock(
        side_effect=[TelegramNetworkError(Mock(), "temporary network issue"), None]
    )
    sleep = AsyncMock()
    monkeypatch.setattr("bot.delivery.asyncio.sleep", sleep)

    await send_message_with_retry(
        bot,
        chat_id=42,
        text="hello",
        reply_markup=None,
        logger=logging.getLogger("test"),
        operation="operator_reply",
    )

    assert bot.send_message.await_count == 2
    sleep.assert_awaited_once()


async def test_send_message_with_retry_honors_retry_after(monkeypatch: MonkeyPatch) -> None:
    bot = Mock()
    bot.send_message = AsyncMock(
        side_effect=[TelegramRetryAfter(Mock(), "too many requests", 4), None]
    )
    sleep = AsyncMock()
    monkeypatch.setattr("bot.delivery.asyncio.sleep", sleep)

    await send_message_with_retry(
        bot,
        chat_id=42,
        text="hello",
        reply_markup=None,
        logger=logging.getLogger("test"),
        operation="apply_macro",
    )

    sleep.assert_awaited_once_with(4)


async def test_send_message_with_retry_raises_after_last_attempt(
    monkeypatch: MonkeyPatch,
) -> None:
    bot = Mock()
    bot.send_message = AsyncMock(side_effect=TelegramNetworkError(Mock(), "still failing"))
    sleep = AsyncMock()
    monkeypatch.setattr("bot.delivery.asyncio.sleep", sleep)

    with pytest.raises(TelegramNetworkError):
        await send_message_with_retry(
            bot,
            chat_id=42,
            text="hello",
            reply_markup=None,
            logger=logging.getLogger("test"),
            operation="operator_reply",
        )

    assert bot.send_message.await_count == 3
    assert sleep.await_count == 2


async def test_send_document_with_retry_recovers_from_network_error(
    monkeypatch: MonkeyPatch,
) -> None:
    bot = Mock()
    bot.send_document = AsyncMock(
        side_effect=[TelegramNetworkError(Mock(), "temporary network issue"), None]
    )
    sleep = AsyncMock()
    monkeypatch.setattr("bot.delivery.asyncio.sleep", sleep)

    await send_document_with_retry(
        bot,
        chat_id=42,
        document=Mock(),
        caption="Отчёт",
        logger=logging.getLogger("test"),
        operation="ticket_report_csv",
    )

    assert bot.send_document.await_count == 2
    sleep.assert_awaited_once()


async def test_deliver_operator_reply_to_client_uses_client_facing_text() -> None:
    bot = Mock()
    bot.send_message = AsyncMock()

    result = await deliver_operator_reply_to_client(
        bot,
        chat_id=42,
        public_number="HD-AAAA1111",
        body="Готово, проверьте еще раз.",
        logger=logging.getLogger("test"),
    )

    assert result is None
    bot.send_message.assert_awaited_once_with(
        42,
        "Ответ по заявке HD-AAAA1111\n\nГотово, проверьте еще раз.",
        reply_markup=None,
    )


async def test_deliver_client_message_to_operator_uses_operator_facing_text() -> None:
    bot = Mock()
    bot.send_message = AsyncMock()

    result = await deliver_client_message_to_operator(
        bot,
        chat_id=1001,
        public_number="HD-AAAA1111",
        body="Есть новости?",
        reply_markup=None,
        active_context=False,
        logger=logging.getLogger("test"),
    )

    assert result is None
    bot.send_message.assert_awaited_once_with(
        1001,
        "Другая заявка · HD-AAAA1111\nТекущий диалог не менялся.\n\nЕсть новости?",
        reply_markup=None,
    )


async def test_deliver_client_message_to_operator_uses_active_ticket_text() -> None:
    bot = Mock()
    bot.send_message = AsyncMock()

    result = await deliver_client_message_to_operator(
        bot,
        chat_id=1001,
        public_number="HD-AAAA1111",
        body="Есть новости?",
        reply_markup=None,
        active_context=True,
        logger=logging.getLogger("test"),
    )

    assert result is None
    bot.send_message.assert_awaited_once_with(
        1001,
        "Текущий диалог · HD-AAAA1111\nКлиент\n\nЕсть новости?",
        reply_markup=None,
    )


async def test_deliver_ticket_closed_to_client_uses_closure_notice() -> None:
    bot = Mock()
    bot.send_message = AsyncMock()
    ticket_public_id = uuid4()

    result = await deliver_ticket_closed_to_client(
        bot,
        chat_id=42,
        public_number="HD-AAAA1111",
        reply_markup=build_ticket_feedback_rating_markup(ticket_public_id=ticket_public_id),
        logger=logging.getLogger("test"),
    )

    assert result is None
    bot.send_message.assert_awaited_once_with(
        42,
        build_ticket_closed_with_feedback_text("HD-AAAA1111"),
        reply_markup=build_ticket_feedback_rating_markup(ticket_public_id=ticket_public_id),
    )


async def test_deliver_ticket_closed_to_operator_uses_operator_notice() -> None:
    bot = Mock()
    bot.send_message = AsyncMock()

    result = await deliver_ticket_closed_to_operator(
        bot,
        chat_id=1001,
        public_number="HD-AAAA1111",
        logger=logging.getLogger("test"),
    )

    assert result is None
    bot.send_message.assert_awaited_once_with(
        1001,
        "Клиент завершил обращение HD-AAAA1111.",
        reply_markup=None,
    )


async def test_deliver_document_to_chat_sends_buffered_file() -> None:
    bot = Mock()
    bot.send_document = AsyncMock()

    result = await deliver_document_to_chat(
        bot,
        chat_id=1001,
        content=b"col1,col2\n1,2\n",
        filename="ticket-report.csv",
        caption="Отчёт по заявке HD-AAAA1111",
        logger=logging.getLogger("test"),
        operation="ticket_report_csv",
    )

    assert result is None
    _, kwargs = bot.send_document.await_args
    assert kwargs["caption"] == "Отчёт по заявке HD-AAAA1111"
    assert kwargs["document"].filename == "ticket-report.csv"


async def test_deliver_client_message_to_operator_uses_local_asset_when_available(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    bot = Mock()
    bot.send_document = AsyncMock()
    asset_root = tmp_path / "assets"
    asset_path = asset_root / "document" / "unique-file-id.pdf"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"pdf")

    monkeypatch.setattr(
        "bot.delivery.get_settings",
        lambda: Mock(assets=Mock(path=asset_root)),
    )

    result = await deliver_client_message_to_operator(
        bot,
        chat_id=1001,
        public_number="HD-AAAA1111",
        text="Посмотрите, пожалуйста.",
        attachment=TicketAttachmentSummary(
            kind=TicketAttachmentKind.DOCUMENT,
            telegram_file_id="telegram-file-id",
            telegram_file_unique_id="unique-file-id",
            filename="guide.pdf",
            mime_type="application/pdf",
            storage_path="document/unique-file-id.pdf",
        ),
        reply_markup=None,
        active_context=False,
        logger=logging.getLogger("test"),
    )

    assert result is None
    _, kwargs = bot.send_document.await_args
    assert kwargs["caption"] == (
        "Другая заявка · HD-AAAA1111\nТекущий диалог не менялся.\n\nФайл · guide.pdf\n\n"
        "Посмотрите, пожалуйста."
    )
    assert kwargs["document"].filename == "guide.pdf"
