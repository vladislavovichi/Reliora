from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk import HelpdeskServiceFactory
from bot.callbacks import OperatorActionCallback, OperatorMacroCallback
from bot.formatters.operator import format_ticket_details
from bot.handlers.operator.common import operator_ticket_action, respond_to_operator
from bot.handlers.operator.parsers import parse_reassign_target, parse_ticket_public_id
from bot.handlers.operator.states import OperatorTicketStates
from bot.keyboards.inline.operator_actions import build_ticket_actions_markup
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_LOCKED_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.operator import (
    APPLY_MACRO_FAILED_TEXT,
    OPERATOR_UNKNOWN_TEXT,
    REASSIGN_CONTEXT_LOST_TEXT,
    REASSIGN_MODE_COMMAND_BLOCK_TEXT,
    REASSIGN_TARGET_PROMPT_TEXT,
    REPLY_CONTEXT_LOST_TEXT,
    REPLY_MODE_COMMAND_BLOCK_TEXT,
    build_client_reply_text,
    build_close_text,
    build_escalate_text,
    build_macro_applied_text,
    build_macro_delivery_failed_text,
    build_macro_saved_text,
    build_macro_sent_text,
    build_reassign_mode_callback_text,
    build_reassign_mode_enabled_text,
    build_reply_delivery_failed_text,
    build_reply_mode_callback_text,
    build_reply_mode_enabled_text,
    build_reply_sent_text,
    build_take_answer_text,
    build_view_opened_text,
)
from domain.enums.tickets import TicketEventType
from domain.tickets import InvalidTicketTransitionError
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorPresenceHelper,
    TicketLockManager,
)

router = Router(name="operator_workflow")


@router.callback_query(OperatorActionCallback.filter(F.action == "view"))
async def handle_view_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
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

    await callback.answer(build_view_opened_text(ticket_details.public_number))
    if callback.message is not None:
        await callback.message.answer(
            format_ticket_details(ticket_details),
            reply_markup=build_ticket_actions_markup(
                ticket_public_id=ticket_details.public_id,
                status=ticket_details.status,
            ),
        )


@router.callback_query(OperatorActionCallback.filter(F.action == "take"))
async def handle_take_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    ticket = None
    ticket_details = None
    error_message: str | None = None

    async with operator_ticket_action(
        callback=callback,
        callback_data=callback_data,
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
        ticket_lock_manager=ticket_lock_manager,
    ) as ticket_public_id:
        if ticket_public_id is None:
            return

        async with helpdesk_service_factory() as helpdesk_service:
            try:
                ticket = await helpdesk_service.assign_ticket_to_operator(
                    ticket_public_id=ticket_public_id,
                    telegram_user_id=callback.from_user.id,
                    display_name=callback.from_user.full_name,
                    username=callback.from_user.username,
                    actor_telegram_user_id=callback.from_user.id,
                )
                if ticket is not None:
                    ticket_details = await helpdesk_service.get_ticket_details(
                        ticket_public_id=ticket.public_id,
                        actor_telegram_user_id=callback.from_user.id,
                    )
            except InvalidTicketTransitionError as exc:
                error_message = str(exc)

    if error_message is not None:
        await respond_to_operator(callback, error_message)
        return

    if ticket is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    answer_text = build_take_answer_text(
        ticket.public_number,
        reassigned=ticket.event_type == TicketEventType.REASSIGNED,
    )

    if callback.message is None or ticket_details is None:
        await respond_to_operator(callback, answer_text)
        return

    await callback.answer(answer_text)
    await callback.message.answer(
        format_ticket_details(ticket_details),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


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

    delivery_error: str | None = None
    try:
        await bot.send_message(macro_result.client_chat_id, macro_result.macro.body)
    except TelegramAPIError as exc:
        delivery_error = str(exc)

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

    delivery_error: str | None = None
    try:
        await bot.send_message(
            reply_result.client_chat_id,
            build_client_reply_text(reply_result.ticket.public_number, message.text),
        )
    except TelegramAPIError as exc:
        delivery_error = str(exc)

    if delivery_error is None:
        await message.answer(build_reply_sent_text(reply_result.ticket.public_number))
    else:
        await message.answer(
            build_reply_delivery_failed_text(reply_result.ticket.public_number, delivery_error)
        )

    if ticket_details is not None:
        await message.answer(
            format_ticket_details(ticket_details),
            reply_markup=build_ticket_actions_markup(
                ticket_public_id=ticket_details.public_id,
                status=ticket_details.status,
            ),
        )


@router.callback_query(OperatorActionCallback.filter(F.action == "reassign"))
async def handle_reassign_action(
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

    await state.set_state(OperatorTicketStates.reassigning)
    await state.update_data(ticket_public_id=str(ticket_public_id))
    await respond_to_operator(
        callback,
        build_reassign_mode_callback_text(ticket_details.public_number),
        build_reassign_mode_enabled_text(),
    )


@router.message(StateFilter(OperatorTicketStates.reassigning), F.text)
async def handle_reassign_message(
    message: Message,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    if message.text is None:
        await message.answer(REASSIGN_TARGET_PROMPT_TEXT)
        return

    if message.text.startswith("/"):
        await message.answer(REASSIGN_MODE_COMMAND_BLOCK_TEXT)
        return

    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    target = parse_reassign_target(message.text)
    if target is None:
        from bot.texts.operator import INVALID_REASSIGN_TARGET_TEXT

        await message.answer(INVALID_REASSIGN_TARGET_TEXT)
        return

    state_data = await state.get_data()
    ticket_public_id = parse_ticket_public_id(state_data.get("ticket_public_id"))
    if ticket_public_id is None:
        await state.clear()
        await message.answer(REASSIGN_CONTEXT_LOST_TEXT)
        return

    actor_telegram_user_id = message.from_user.id if message.from_user is not None else None
    lock = ticket_lock_manager.for_ticket(str(ticket_public_id))
    if not await lock.acquire():
        await message.answer(TICKET_LOCKED_TEXT)
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            try:
                ticket = await helpdesk_service.assign_ticket_to_operator(
                    ticket_public_id=ticket_public_id,
                    telegram_user_id=target[0],
                    display_name=target[1],
                    username=None,
                    actor_telegram_user_id=actor_telegram_user_id,
                )
            except InvalidTicketTransitionError as exc:
                await state.clear()
                await message.answer(str(exc))
                return

            if ticket is None:
                await state.clear()
                await message.answer(TICKET_NOT_FOUND_TEXT)
                return

            ticket_details = await helpdesk_service.get_ticket_details(
                ticket_public_id=ticket_public_id,
                actor_telegram_user_id=actor_telegram_user_id,
            )
    finally:
        await lock.release()

    await state.clear()

    if ticket_details is None:
        await message.answer(build_take_answer_text(ticket.public_number, reassigned=False))
        return

    await message.answer(
        build_take_answer_text(
            ticket.public_number,
            reassigned=ticket.event_type == TicketEventType.REASSIGNED,
        )
    )
    await message.answer(
        format_ticket_details(ticket_details),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "close"))
async def handle_close_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    ticket = None
    ticket_details = None
    error_message: str | None = None

    async with operator_ticket_action(
        callback=callback,
        callback_data=callback_data,
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
        ticket_lock_manager=ticket_lock_manager,
    ) as ticket_public_id:
        if ticket_public_id is None:
            return

        async with helpdesk_service_factory() as helpdesk_service:
            try:
                ticket = await helpdesk_service.close_ticket_as_operator(
                    ticket_public_id=ticket_public_id,
                    actor_telegram_user_id=callback.from_user.id,
                )
                if ticket is not None:
                    ticket_details = await helpdesk_service.get_ticket_details(
                        ticket_public_id=ticket_public_id,
                        actor_telegram_user_id=callback.from_user.id,
                    )
            except InvalidTicketTransitionError as exc:
                error_message = str(exc)

    if error_message is not None:
        await respond_to_operator(callback, error_message)
        return

    if ticket is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    answer_text = build_close_text(ticket.public_number)
    if callback.message is None or ticket_details is None:
        await respond_to_operator(callback, answer_text)
        return

    await callback.answer(answer_text)
    await callback.message.answer(
        format_ticket_details(ticket_details),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "escalate"))
async def handle_escalate_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    ticket = None
    ticket_details = None
    error_message: str | None = None

    async with operator_ticket_action(
        callback=callback,
        callback_data=callback_data,
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
        ticket_lock_manager=ticket_lock_manager,
    ) as ticket_public_id:
        if ticket_public_id is None:
            return

        async with helpdesk_service_factory() as helpdesk_service:
            try:
                ticket = await helpdesk_service.escalate_ticket_as_operator(
                    ticket_public_id=ticket_public_id,
                    actor_telegram_user_id=callback.from_user.id,
                )
                if ticket is not None:
                    ticket_details = await helpdesk_service.get_ticket_details(
                        ticket_public_id=ticket_public_id,
                        actor_telegram_user_id=callback.from_user.id,
                    )
            except InvalidTicketTransitionError as exc:
                error_message = str(exc)

    if error_message is not None:
        await respond_to_operator(callback, error_message)
        return

    if ticket is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    answer_text = build_escalate_text(ticket.public_number)
    if callback.message is None or ticket_details is None:
        await respond_to_operator(callback, answer_text)
        return

    await callback.answer(answer_text)
    await callback.message.answer(
        format_ticket_details(ticket_details),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )
