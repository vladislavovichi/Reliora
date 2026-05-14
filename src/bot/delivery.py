import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import BufferedInputFile, FSInputFile, InlineKeyboardMarkup
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception_type, stop_after_attempt

from application.use_cases.tickets.summaries import TicketAttachmentSummary
from bot.texts.feedback import build_ticket_closed_with_feedback_text
from bot.texts.operator import build_client_finished_ticket_text
from bot.texts.ticket_messages import build_client_delivery_body, build_operator_delivery_body
from infrastructure.assets.storage import LocalTicketAssetStorage
from infrastructure.config.settings import get_settings

_RETRYABLE_TELEGRAM_ERRORS = (
    TelegramRetryAfter,
    TelegramNetworkError,
    TelegramServerError,
    TimeoutError,
)


async def send_message_with_retry(
    bot: Bot,
    *,
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    logger: logging.Logger,
    operation: str,
) -> None:
    await _run_telegram_delivery_with_retry(
        lambda: bot.send_message(chat_id, text, reply_markup=reply_markup),
        logger=logger,
        operation=operation,
        chat_id=chat_id,
    )


async def send_document_with_retry(bot: Bot, **kwargs: Any) -> None:
    await _send_with_retry(bot.send_document, **kwargs)


async def send_photo_with_retry(bot: Bot, **kwargs: Any) -> None:
    await _send_with_retry(bot.send_photo, **kwargs)


async def send_voice_with_retry(bot: Bot, **kwargs: Any) -> None:
    await _send_with_retry(bot.send_voice, **kwargs)


async def send_video_with_retry(bot: Bot, **kwargs: Any) -> None:
    await _send_with_retry(bot.send_video, **kwargs)


async def _send_with_retry(
    send_operation: Callable[..., Awaitable[object]],
    *,
    logger: logging.Logger,
    operation: str,
    chat_id: int,
    **kwargs: Any,
) -> None:
    await _run_telegram_delivery_with_retry(
        lambda: send_operation(chat_id=chat_id, **kwargs),
        logger=logger,
        operation=operation,
        chat_id=chat_id,
    )


async def _run_telegram_delivery_with_retry(
    send: Callable[[], Awaitable[object]],
    *,
    logger: logging.Logger,
    operation: str,
    chat_id: int,
) -> None:
    attempts, timeout = _resolve_delivery_policy()
    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type(_RETRYABLE_TELEGRAM_ERRORS),
        stop=stop_after_attempt(attempts),
        wait=_telegram_retry_wait,
        sleep=_telegram_retry_sleep,
        after=_log_telegram_delivery_failure(
            logger,
            operation=operation,
            chat_id=chat_id,
            timeout=timeout,
        ),
        reraise=True,
    ):
        with attempt:
            attempt_number = attempt.retry_state.attempt_number
            await asyncio.wait_for(send(), timeout=timeout)
            if attempt_number > 1:
                logger.info(
                    "Telegram delivery recovered operation=%s chat_id=%s attempt=%s",
                    operation,
                    chat_id,
                    attempt_number,
                )
            return


def _log_telegram_delivery_failure(
    logger: logging.Logger,
    *,
    operation: str,
    chat_id: int,
    timeout: float,
) -> Callable[[RetryCallState], None]:
    def log_failure(retry_state: RetryCallState) -> None:
        if retry_state.outcome is None:
            return
        exc = retry_state.outcome.exception()
        if exc is None:
            return
        attempt = retry_state.attempt_number
        if isinstance(exc, TelegramRetryAfter):
            logger.warning(
                "Telegram delivery rate-limited operation=%s chat_id=%s attempt=%s retry_after=%s",
                operation,
                chat_id,
                attempt,
                exc.retry_after,
            )
            return
        if isinstance(exc, (TelegramNetworkError, TelegramServerError)):
            logger.warning(
                "Telegram delivery transient failure operation=%s chat_id=%s attempt=%s error=%s",
                operation,
                chat_id,
                attempt,
                exc,
            )
            return
        if isinstance(exc, TimeoutError):
            logger.warning(
                "Telegram delivery timeout operation=%s chat_id=%s attempt=%s timeout_seconds=%s",
                operation,
                chat_id,
                attempt,
                timeout,
            )

    return log_failure


def _telegram_retry_wait(retry_state: RetryCallState) -> float:
    if retry_state.outcome is not None:
        exc = retry_state.outcome.exception()
        if isinstance(exc, TelegramRetryAfter):
            retry_after = exc.retry_after
            if not isinstance(retry_after, (int, float)):
                retry_after = 1
            return float(min(max(retry_after, 1), 5))
    return float(min(0.5 * (2 ** (retry_state.attempt_number - 1)), 2.0))


async def _telegram_retry_sleep(delay: float) -> None:
    await asyncio.sleep(delay)


async def deliver_operator_reply_to_client(
    bot: Bot,
    *,
    chat_id: int,
    public_number: str,
    text: str | None = None,
    body: str | None = None,
    attachment: TicketAttachmentSummary | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
    logger: logging.Logger,
) -> str | None:
    effective_text = text if text is not None else body
    return await _deliver_message(
        bot,
        chat_id=chat_id,
        text=build_client_delivery_body(
            public_number=public_number,
            text=effective_text,
            attachment=attachment,
        ),
        attachment=attachment,
        reply_markup=reply_markup,
        logger=logger,
        operation="operator_reply",
    )


async def deliver_client_message_to_operator(
    bot: Bot,
    *,
    chat_id: int,
    public_number: str,
    text: str | None = None,
    body: str | None = None,
    attachment: TicketAttachmentSummary | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
    active_context: bool = False,
    logger: logging.Logger,
) -> str | None:
    effective_text = text if text is not None else body
    return await _deliver_message(
        bot,
        chat_id=chat_id,
        text=build_operator_delivery_body(
            public_number=public_number,
            text=effective_text,
            attachment=attachment,
            active_context=active_context,
        ),
        attachment=attachment,
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


async def deliver_document_to_chat(
    bot: Bot,
    *,
    chat_id: int,
    content: bytes,
    filename: str,
    caption: str | None = None,
    logger: logging.Logger,
    operation: str,
) -> str | None:
    try:
        await send_document_with_retry(
            bot,
            chat_id=chat_id,
            document=BufferedInputFile(content, filename=filename),
            caption=caption,
            logger=logger,
            operation=operation,
        )
    except TelegramAPIError as exc:
        return str(exc)
    return None


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


async def _deliver_message(
    bot: Bot,
    *,
    chat_id: int,
    text: str,
    attachment: TicketAttachmentSummary | None,
    reply_markup: InlineKeyboardMarkup | None,
    logger: logging.Logger,
    operation: str,
) -> str | None:
    if attachment is None:
        return await _deliver_text(
            bot,
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            logger=logger,
            operation=operation,
        )

    try:
        await _send_attachment_with_retry(
            bot,
            chat_id=chat_id,
            attachment=attachment,
            caption=text,
            reply_markup=reply_markup,
            logger=logger,
            operation=operation,
        )
    except TelegramAPIError as exc:
        return str(exc)
    return None


async def _send_attachment_with_retry(
    bot: Bot,
    *,
    chat_id: int,
    attachment: TicketAttachmentSummary,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None,
    logger: logging.Logger,
    operation: str,
) -> None:
    local_attachment = _build_local_input_file(attachment)

    if attachment.kind.value == "photo":
        await send_photo_with_retry(
            bot,
            chat_id=chat_id,
            photo=local_attachment or attachment.telegram_file_id,
            caption=caption,
            reply_markup=reply_markup,
            logger=logger,
            operation=operation,
        )
        return
    if attachment.kind.value == "voice":
        await send_voice_with_retry(
            bot,
            chat_id=chat_id,
            voice=local_attachment or attachment.telegram_file_id,
            caption=caption,
            reply_markup=reply_markup,
            logger=logger,
            operation=operation,
        )
        return
    if attachment.kind.value == "video":
        await send_video_with_retry(
            bot,
            chat_id=chat_id,
            video=local_attachment or attachment.telegram_file_id,
            caption=caption,
            reply_markup=reply_markup,
            logger=logger,
            operation=operation,
        )
        return
    await send_document_with_retry(
        bot,
        chat_id=chat_id,
        document=local_attachment or attachment.telegram_file_id,
        caption=caption,
        reply_markup=reply_markup,
        logger=logger,
        operation=operation,
    )


def _build_local_input_file(attachment: TicketAttachmentSummary) -> FSInputFile | None:
    if not attachment.storage_path:
        return None
    storage = LocalTicketAssetStorage(get_settings().assets.path)
    try:
        absolute_path = storage.resolve_path(attachment.storage_path)
    except ValueError:
        return None
    if not absolute_path.exists():
        return None
    return FSInputFile(absolute_path, filename=attachment.filename)


def _resolve_delivery_policy() -> tuple[int, float]:
    settings = get_settings()
    resilience = getattr(settings, "resilience", None)
    attempts = getattr(resilience, "telegram_send_attempts", 3)
    timeout = getattr(resilience, "telegram_send_timeout_seconds", 10.0)
    safe_attempts = attempts if isinstance(attempts, int) else 3
    safe_timeout = timeout if isinstance(timeout, (int, float)) else 10.0
    return max(safe_attempts, 1), max(float(safe_timeout), 0.1)
