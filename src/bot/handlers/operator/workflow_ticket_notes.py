from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from bot.callbacks import OperatorActionCallback
from bot.formatters.operator_ticket_views import (
    format_ticket_notes_chunks,
    format_ticket_notes_text,
)
from bot.handlers.operator.active_context import activate_ticket_for_operator
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.handlers.operator.states import OperatorTicketStates
from bot.keyboards.inline.operator_actions import build_ticket_notes_markup
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.operator import (
    NOTE_CONTEXT_LOST_TEXT,
    NOTE_MODE_COMMAND_BLOCK_TEXT,
    NOTE_PROMPT_TEXT,
    build_note_saved_text,
    build_notes_opened_text,
)
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    TicketLiveSessionStore,
    TicketLockManager,
)

router = Router(name="operator_workflow_ticket_notes")
logger = logging.getLogger(__name__)


@router.callback_query(OperatorActionCallback.filter(F.action == "notes"))
async def handle_notes_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
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

    await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )
    if not isinstance(callback.message, Message):
        await callback.answer(build_notes_opened_text(ticket_details.public_number))
        return

    await callback.answer(build_notes_opened_text(ticket_details.public_number))
    await callback.message.edit_text(
        format_ticket_notes_text(ticket_details),
        reply_markup=build_ticket_notes_markup(ticket_public_id=ticket_details.public_id),
    )
    for chunk in format_ticket_notes_chunks(ticket_details):
        await callback.message.answer(chunk)


@router.callback_query(OperatorActionCallback.filter(F.action == "note_add"))
async def handle_note_add_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
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

    await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )
    await state.set_state(OperatorTicketStates.writing_note)
    await state.set_data({"ticket_public_id": str(ticket_details.public_id)})
    await callback.answer(build_notes_opened_text(ticket_details.public_number))
    if isinstance(callback.message, Message):
        await callback.message.answer(NOTE_PROMPT_TEXT)


@router.message(StateFilter(OperatorTicketStates.writing_note), F.text)
async def handle_note_message(
    message: Message,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_lock_manager: TicketLockManager,
) -> None:
    if message.from_user is None:
        await message.answer(NOTE_CONTEXT_LOST_TEXT)
        return
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    state_data = await state.get_data()
    ticket_public_id = parse_ticket_public_id(
        state_data.get("ticket_public_id")
        if isinstance(state_data.get("ticket_public_id"), str)
        else None
    )
    if ticket_public_id is None:
        await state.clear()
        await message.answer(NOTE_CONTEXT_LOST_TEXT)
        return

    await operator_presence.touch(operator_id=message.from_user.id)
    lock = ticket_lock_manager.for_ticket(str(ticket_public_id))
    if not await lock.acquire():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            note_ticket = await helpdesk_service.add_internal_note_to_ticket(
                ticket_public_id=ticket_public_id,
                telegram_user_id=message.from_user.id,
                display_name=message.from_user.full_name,
                username=message.from_user.username,
                text=message.text,
                actor_telegram_user_id=message.from_user.id,
            )
            ticket_details = await helpdesk_service.get_ticket_details(
                ticket_public_id=ticket_public_id,
                actor_telegram_user_id=message.from_user.id,
            )
    finally:
        await lock.release()
        await state.clear()

    if note_ticket is None or ticket_details is None:
        await message.answer(NOTE_CONTEXT_LOST_TEXT)
        return

    await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=message.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )
    await message.answer(build_note_saved_text(ticket_details.public_number))
    await message.answer(
        format_ticket_notes_text(ticket_details),
        reply_markup=build_ticket_notes_markup(ticket_public_id=ticket_details.public_id),
    )
    for chunk in format_ticket_notes_chunks(ticket_details):
        await message.answer(chunk)


@router.message(StateFilter(OperatorTicketStates.writing_note))
async def handle_non_text_note_message(message: Message) -> None:
    await message.answer(NOTE_MODE_COMMAND_BLOCK_TEXT)
