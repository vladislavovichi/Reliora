from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.types import CallbackQuery

from application.services.helpdesk.service import HelpdeskServiceFactory
from bot.callbacks import OperatorMacroCallback
from bot.delivery import deliver_text_to_chat
from bot.formatters.operator import format_ticket_details
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.keyboards.inline.operator_actions import build_ticket_actions_markup
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_LOCKED_TEXT,
)
from bot.texts.operator import (
    APPLY_MACRO_FAILED_TEXT,
    build_macro_applied_text,
    build_macro_delivery_failed_text,
    build_macro_saved_text,
    build_macro_sent_text,
)
from domain.tickets import InvalidTicketTransitionError
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorPresenceHelper,
    TicketLockManager,
)

router = Router(name="operator_workflow_macro_actions")
logger = logging.getLogger(__name__)


@router.callback_query(OperatorMacroCallback.filter())
async def handle_apply_macro(
    callback: CallbackQuery,
    callback_data: OperatorMacroCallback,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await respond_to_operator(callback, INVALID_TICKET_ID_TEXT)
        return
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    lock = ticket_lock_manager.for_ticket(callback_data.ticket_public_id)
    if not await lock.acquire():
        await respond_to_operator(callback, TICKET_LOCKED_TEXT)
        return

    macro_result = None
    ticket_details = None
    error_message: str | None = None
    try:
        async with helpdesk_service_factory() as helpdesk_service:
            try:
                macro_result = await helpdesk_service.apply_macro_to_ticket(
                    ticket_public_id=ticket_public_id,
                    macro_id=callback_data.macro_id,
                    telegram_user_id=callback.from_user.id,
                    display_name=callback.from_user.full_name,
                    username=callback.from_user.username,
                    actor_telegram_user_id=callback.from_user.id,
                )
                if macro_result is not None:
                    ticket_details = await helpdesk_service.get_ticket_details(
                        ticket_public_id=ticket_public_id,
                        actor_telegram_user_id=callback.from_user.id,
                    )
            except InvalidTicketTransitionError as exc:
                error_message = str(exc)
    finally:
        await lock.release()

    if error_message is not None:
        await respond_to_operator(callback, error_message)
        return
    if macro_result is None:
        await respond_to_operator(callback, APPLY_MACRO_FAILED_TEXT)
        return

    delivery_error = await _deliver_macro(
        bot=bot,
        chat_id=macro_result.client_chat_id,
        body=macro_result.macro.body,
    )
    if callback.message is None or ticket_details is None:
        answer_text = build_macro_applied_text(macro_result.macro.title)
        if delivery_error is not None:
            answer_text = build_macro_delivery_failed_text(
                macro_result.macro.title,
                delivery_error,
            )
        await respond_to_operator(callback, answer_text)
        return

    if delivery_error is None:
        await callback.answer(build_macro_sent_text(macro_result.macro.title))
    else:
        await callback.answer(build_macro_saved_text(macro_result.macro.title))
        await callback.message.answer(
            build_macro_delivery_failed_text(macro_result.macro.title, delivery_error)
        )

    await callback.message.answer(
        format_ticket_details(ticket_details),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


async def _deliver_macro(*, bot: Bot, chat_id: int, body: str) -> str | None:
    return await deliver_text_to_chat(
        bot,
        chat_id=chat_id,
        text=body,
        logger=logger,
        operation="apply_macro",
    )
