from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from bot.callbacks import OperatorActionCallback
from bot.delivery import deliver_operator_reply_to_client
from bot.formatters.operator import format_ticket_details
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.handlers.operator.states import OperatorTicketStates
from bot.keyboards.inline.operator_actions import build_ticket_actions_markup
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_LOCKED_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.operator import (
    OPERATOR_UNKNOWN_TEXT,
    REPLY_CONTEXT_LOST_TEXT,
    REPLY_MODE_COMMAND_BLOCK_TEXT,
    build_reply_delivery_failed_text,
    build_reply_mode_callback_text,
    build_reply_mode_enabled_text,
    build_reply_sent_text,
)
from domain.tickets import InvalidTicketTransitionError
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorPresenceHelper,
    TicketLockManager,
)

router = Router(name="operator_workflow_reply")
logger = logging.getLogger(__name__)


@router.callback_query(OperatorActionCallback.filter(F.action == "reply"))
async def handle_reply_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await respond_to_operator(callback, INVALID_TICKET_ID_TEXT)
        return
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor_telegram_user_id=callback.from_user.id,
        )

    if ticket_details is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    await state.set_state(OperatorTicketStates.replying)
    await state.update_data(ticket_public_id=str(ticket_public_id))
    await respond_to_operator(
        callback,
        build_reply_mode_callback_text(ticket_details.public_number),
        build_reply_mode_enabled_text(ticket_details.public_number),
    )


@router.message(StateFilter(OperatorTicketStates.replying), F.text)
async def handle_reply_message(
    message: Message,
    state: FSMContext,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    if message.from_user is None or message.text is None:
        await message.answer(OPERATOR_UNKNOWN_TEXT)
        return
    if message.text.startswith("/"):
        await message.answer(REPLY_MODE_COMMAND_BLOCK_TEXT)
        return
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=message.from_user.id)

    state_data = await state.get_data()
    ticket_public_id = parse_ticket_public_id(state_data.get("ticket_public_id"))
    if ticket_public_id is None:
        await state.clear()
        await message.answer(REPLY_CONTEXT_LOST_TEXT)
        return

    lock = ticket_lock_manager.for_ticket(str(ticket_public_id))
    if not await lock.acquire():
        await message.answer(TICKET_LOCKED_TEXT)
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            try:
                reply_result = await helpdesk_service.reply_to_ticket_as_operator(
                    ticket_public_id=ticket_public_id,
                    telegram_user_id=message.from_user.id,
                    display_name=message.from_user.full_name,
                    username=message.from_user.username,
                    telegram_message_id=message.message_id,
                    text=message.text,
                    actor_telegram_user_id=message.from_user.id,
                )
            except InvalidTicketTransitionError as exc:
                await state.clear()
                await message.answer(str(exc))
                return

            if reply_result is None:
                await state.clear()
                await message.answer(TICKET_NOT_FOUND_TEXT)
                return

            ticket_details = await helpdesk_service.get_ticket_details(
                ticket_public_id=ticket_public_id,
                actor_telegram_user_id=message.from_user.id,
            )
    finally:
        await lock.release()

    await state.clear()
    logger.info(
        "Operator reply stored operator_id=%s ticket=%s",
        message.from_user.id,
        reply_result.ticket.public_number,
    )

    delivery_error = await _deliver_reply(
        bot=bot,
        chat_id=reply_result.client_chat_id,
        public_number=reply_result.ticket.public_number,
        body=message.text,
    )
    if delivery_error is None:
        await message.answer(build_reply_sent_text(reply_result.ticket.public_number))
    else:
        await message.answer(
            build_reply_delivery_failed_text(reply_result.ticket.public_number, delivery_error)
        )

    if ticket_details is None:
        return

    await message.answer(
        format_ticket_details(ticket_details),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


async def _deliver_reply(
    *,
    bot: Bot,
    chat_id: int,
    public_number: str,
    body: str,
) -> str | None:
    return await deliver_operator_reply_to_client(
        bot,
        chat_id=chat_id,
        public_number=public_number,
        body=body,
        logger=logger,
    )
