from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from bot.callbacks import OperatorActionCallback
from bot.formatters.operator import format_ticket_details
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_reassign_target, parse_ticket_public_id
from bot.handlers.operator.states import OperatorTicketStates
from bot.keyboards.inline.operator_actions import build_ticket_actions_markup
from bot.texts.buttons import ALL_NAVIGATION_BUTTONS, CANCEL_BUTTON_TEXT
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_LOCKED_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.operator import (
    INVALID_REASSIGN_TARGET_TEXT,
    OPERATOR_INPUT_NAVIGATION_BLOCK_TEXT,
    REASSIGN_CONTEXT_LOST_TEXT,
    REASSIGN_MODE_COMMAND_BLOCK_TEXT,
    REASSIGN_TARGET_PROMPT_TEXT,
    build_reassign_mode_callback_text,
    build_reassign_mode_enabled_text,
    build_take_answer_text,
)
from domain.enums.tickets import TicketEventType
from domain.tickets import InvalidTicketTransitionError
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorPresenceHelper,
    TicketLockManager,
)

router = Router(name="operator_workflow_reassignment")


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
    if message.text in ALL_NAVIGATION_BUTTONS and message.text != CANCEL_BUTTON_TEXT:
        await message.answer(OPERATOR_INPUT_NAVIGATION_BLOCK_TEXT)
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
    await message.answer(
        build_take_answer_text(
            ticket.public_number,
            reassigned=ticket.event_type == TicketEventType.REASSIGNED,
        )
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
