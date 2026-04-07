from __future__ import annotations

import logging
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from pytest import MonkeyPatch

from bot.delivery import (
    deliver_client_message_to_operator,
    deliver_operator_reply_to_client,
    deliver_ticket_closed_to_client,
    send_message_with_retry,
)


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
            logger=logging.getLogger("test"),
            operation="operator_reply",
        )

    assert bot.send_message.await_count == 3
    assert sleep.await_count == 2


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
    )


async def test_deliver_client_message_to_operator_uses_operator_facing_text() -> None:
    bot = Mock()
    bot.send_message = AsyncMock()

    result = await deliver_client_message_to_operator(
        bot,
        chat_id=1001,
        public_number="HD-AAAA1111",
        body="Есть новости?",
        logger=logging.getLogger("test"),
    )

    assert result is None
    bot.send_message.assert_awaited_once_with(
        1001,
        "Новое сообщение в заявке HD-AAAA1111\n\nЕсть новости?",
    )


async def test_deliver_ticket_closed_to_client_uses_closure_notice() -> None:
    bot = Mock()
    bot.send_message = AsyncMock()

    result = await deliver_ticket_closed_to_client(
        bot,
        chat_id=42,
        public_number="HD-AAAA1111",
        logger=logging.getLogger("test"),
    )

    assert result is None
    bot.send_message.assert_awaited_once_with(
        42,
        "Заявка HD-AAAA1111 закрыта. Если вопрос останется, просто напишите в чат.",
    )
