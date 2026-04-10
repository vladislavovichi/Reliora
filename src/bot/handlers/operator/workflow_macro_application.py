from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import (
    build_apply_macro_command,
    build_operator_identity,
    build_request_actor,
)
from bot.callbacks import OperatorMacroCallback
from bot.delivery import deliver_text_to_chat
from bot.handlers.operator.active_context import activate_ticket_for_operator
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.handlers.operator.ticket_surfaces import edit_ticket_main_message
from bot.keyboards.inline.client_actions import build_client_ticket_markup
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_LOCKED_TEXT,
)
from bot.texts.operator import (
    APPLY_MACRO_FAILED_TEXT,
    build_macro_delivery_failed_text,
    build_macro_saved_text,
    build_macro_sent_text,
)
from domain.tickets import InvalidTicketTransitionError
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    TicketLiveSessionStore,
    TicketLockManager,
)

router = Router(name="operator_workflow_macro_application")
logger = logging.getLogger(__name__)


@router.callback_query(OperatorMacroCallback.filter(F.action == "apply"))
async def handle_apply_macro(
    callback: CallbackQuery,
    callback_data: OperatorMacroCallback,
    bot: Bot,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
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
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            try:
                operator = build_operator_identity(callback.from_user)
                if operator is None:
                    await respond_to_operator(callback, APPLY_MACRO_FAILED_TEXT)
                    return
                macro_result = await helpdesk_backend.apply_macro_to_ticket(
                    build_apply_macro_command(
                        ticket_public_id=ticket_public_id,
                        macro_id=callback_data.macro_id,
                        operator=operator,
                    ),
                    actor=build_request_actor(callback.from_user),
                )
            except InvalidTicketTransitionError as exc:
                error_message = str(exc)

            if macro_result is not None:
                ticket_details = await helpdesk_backend.get_ticket_details(
                    ticket_public_id=ticket_public_id,
                    actor=build_request_actor(callback.from_user),
                )
    finally:
        await lock.release()

    if error_message is not None:
        await respond_to_operator(callback, error_message)
        return
    if macro_result is None:
        await respond_to_operator(callback, APPLY_MACRO_FAILED_TEXT)
        return

    is_active_context = False
    if ticket_details is not None:
        is_active_context = await activate_ticket_for_operator(
            active_ticket_store=operator_active_ticket_store,
            operator_telegram_user_id=callback.from_user.id,
            ticket_details=ticket_details,
            ticket_live_session_store=ticket_live_session_store,
        )

    delivery_error = await deliver_text_to_chat(
        bot,
        chat_id=macro_result.client_chat_id,
        text=macro_result.macro.body,
        reply_markup=build_client_ticket_markup(ticket_public_id=ticket_public_id),
        logger=logger,
        operation="apply_macro",
    )

    answer_text = build_macro_sent_text(macro_result.macro.title)
    if delivery_error is not None:
        answer_text = build_macro_saved_text(macro_result.macro.title)

    if not isinstance(callback.message, Message) or ticket_details is None:
        message_text = None
        if delivery_error is not None:
            message_text = build_macro_delivery_failed_text(
                macro_result.macro.title,
                delivery_error,
            )
        await respond_to_operator(callback, answer_text, message_text)
        return

    await callback.answer(answer_text)
    if delivery_error is not None:
        await callback.message.answer(
            build_macro_delivery_failed_text(macro_result.macro.title, delivery_error)
        )

    await edit_ticket_main_message(
        message=callback.message,
        ticket_details=ticket_details,
        is_active_context=is_active_context,
    )
