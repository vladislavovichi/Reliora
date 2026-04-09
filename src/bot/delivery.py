from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import InlineKeyboardMarkup

from bot.texts.client import build_operator_reply_text
from bot.texts.feedback import build_ticket_closed_with_feedback_text
from bot.texts.operator import (
    build_active_client_message_text,
    build_client_finished_ticket_text,
    build_forwarded_client_message_text,
)

DEFAULT_SEND_ATTEMPTS = 3


async def send_message_with_retry(
    bot: Bot,
    *,
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    logger: logging.Logger,
    operation: str,
) -> None:
    for attempt in range(1, DEFAULT_SEND_ATTEMPTS + 1):
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
            if attempt > 1:
                logger.info(
                    "Telegram delivery recovered operation=%s chat_id=%s attempt=%s",
                    operation,
                    chat_id,
                    attempt,
                )
            return
        except TelegramRetryAfter as exc:
            logger.warning(
                "Telegram delivery rate-limited operation=%s chat_id=%s attempt=%s retry_after=%s",
                operation,
                chat_id,
                attempt,
                exc.retry_after,
            )
            if attempt >= DEFAULT_SEND_ATTEMPTS:
                raise
            await asyncio.sleep(min(max(exc.retry_after, 1), 5))
        except (TelegramNetworkError, TelegramServerError) as exc:
            logger.warning(
                "Telegram delivery transient failure operation=%s chat_id=%s attempt=%s error=%s",
                operation,
                chat_id,
                attempt,
                exc,
            )
            if attempt >= DEFAULT_SEND_ATTEMPTS:
                raise
            await asyncio.sleep(min(0.5 * (2 ** (attempt - 1)), 2.0))
        except TelegramAPIError:
            raise


async def deliver_operator_reply_to_client(
    bot: Bot,
    *,
    chat_id: int,
    public_number: str,
    body: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    logger: logging.Logger,
) -> str | None:
    return await _deliver_text(
        bot,
        chat_id=chat_id,
        text=build_operator_reply_text(public_number, body),
        reply_markup=reply_markup,
        logger=logger,
        operation="operator_reply",
    )


async def deliver_client_message_to_operator(
    bot: Bot,
    *,
    chat_id: int,
    public_number: str,
    body: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    active_context: bool = False,
    logger: logging.Logger,
) -> str | None:
    return await _deliver_text(
        bot,
        chat_id=chat_id,
        text=(
            build_active_client_message_text(public_number, body)
            if active_context
            else build_forwarded_client_message_text(public_number, body)
        ),
        reply_markup=reply_markup,
        logger=logger,
        operation="client_message_forward",
    )


async def deliver_ticket_closed_to_client(
    bot: Bot,
    *,
    chat_id: int,
    public_number: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    logger: logging.Logger,
) -> str | None:
    return await _deliver_text(
        bot,
        chat_id=chat_id,
        text=build_ticket_closed_with_feedback_text(public_number),
        reply_markup=reply_markup,
        logger=logger,
        operation="ticket_closed",
    )


async def deliver_ticket_closed_to_operator(
    bot: Bot,
    *,
    chat_id: int,
    public_number: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    logger: logging.Logger,
) -> str | None:
    return await _deliver_text(
        bot,
        chat_id=chat_id,
        text=build_client_finished_ticket_text(public_number),
        reply_markup=reply_markup,
        logger=logger,
        operation="ticket_closed_by_client",
    )


async def deliver_text_to_chat(
    bot: Bot,
    *,
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    logger: logging.Logger,
    operation: str,
) -> str | None:
    return await _deliver_text(
        bot,
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        logger=logger,
        operation=operation,
    )


async def _deliver_text(
    bot: Bot,
    *,
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
    logger: logging.Logger,
    operation: str,
) -> str | None:
    try:
        await send_message_with_retry(
            bot,
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            logger=logger,
            operation=operation,
        )
    except TelegramAPIError as exc:
        return str(exc)
    return None
