from __future__ import annotations

import logging
from collections.abc import Sequence
from math import ceil

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.summaries import (
    MacroSummary,
    OperatorTicketSummary,
    QueuedTicketSummary,
)
from bot.callbacks import OperatorQueueCallback
from bot.formatters.macros import (
    format_admin_macro_details,
    format_admin_macro_list,
    paginate_macros,
)
from bot.formatters.operator import (
    QUEUE_PAGE_SIZE,
    format_operator_list_response,
    format_operator_ticket_page,
    format_queue_page,
)
from bot.handlers.operator.active_context import activate_ticket_for_operator
from bot.handlers.admin.states import AdminMacroStates, AdminOperatorStates
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.handlers.operator.states import OperatorTicketStates
from bot.keyboards.inline.admin import build_operator_management_markup
from bot.keyboards.inline.macros import (
    build_admin_macro_detail_markup,
    build_admin_macro_list_markup,
)
from bot.keyboards.inline.operator_actions import (
    build_operator_ticket_list_markup,
    build_queue_markup,
)
from bot.texts.buttons import (
    CANCEL_BUTTON_TEXT,
    MY_TICKETS_BUTTON_TEXT,
    QUEUE_BUTTON_TEXT,
    TAKE_NEXT_BUTTON_TEXT,
)
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from bot.texts.operator import (
    MY_TICKETS_EMPTY_TEXT,
    NO_QUEUE_TICKETS_TEXT,
    OPERATOR_ACTION_CANCELLED_TEXT,
    OPERATOR_ACTION_IDLE_TEXT,
    OPERATOR_UNKNOWN_TEXT,
    QUEUE_BUSY_TEXT,
    QUEUE_EMPTY_TEXT,
    build_queue_page_callback_text,
)
from infrastructure.config.settings import Settings
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    TicketLiveSessionStore,
    TicketLockManager,
)

MACRO_CREATE_STATE_NAMES = {
    AdminMacroStates.creating_title.state,
    AdminMacroStates.creating_body.state,
    AdminMacroStates.creating_preview.state,
}
MACRO_EDIT_STATE_NAMES = {
    AdminMacroStates.editing_title.state,
    AdminMacroStates.editing_body.state,
}
OPERATOR_TICKET_STATE_NAMES = {
    OperatorTicketStates.replying.state,
    OperatorTicketStates.reassigning.state,
}

router = Router(name="operator_navigation")
logger = logging.getLogger(__name__)


@router.message(F.text == CANCEL_BUTTON_TEXT)
async def handle_cancel(
    message: Message,
    state: FSMContext,
    settings: Settings,
    helpdesk_service_factory: HelpdeskServiceFactory,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
) -> None:
    state_name = await state.get_state()
    if state_name is None:
        await message.answer(OPERATOR_ACTION_IDLE_TEXT)
        return

    state_data = await state.get_data()
    await state.clear()
    await message.answer(OPERATOR_ACTION_CANCELLED_TEXT)
    if message.from_user is None:
        return

    if state_name in OPERATOR_TICKET_STATE_NAMES:
        await _restore_ticket_after_cancel(
            message=message,
            state_data=state_data,
            helpdesk_service_factory=helpdesk_service_factory,
            operator_active_ticket_store=operator_active_ticket_store,
            ticket_live_session_store=ticket_live_session_store,
        )
        return
    if state_name == AdminOperatorStates.adding_operator.state:
        await _restore_operator_directory_after_cancel(
            message=message,
            settings=settings,
            helpdesk_service_factory=helpdesk_service_factory,
        )
        return
    if state_name in MACRO_CREATE_STATE_NAMES:
        await _restore_macro_list_after_cancel(
            message=message,
            state_data=state_data,
            helpdesk_service_factory=helpdesk_service_factory,
        )
        return
    if state_name in MACRO_EDIT_STATE_NAMES:
        await _restore_macro_details_after_cancel(
            message=message,
            state_data=state_data,
            helpdesk_service_factory=helpdesk_service_factory,
        )
        return


@router.message(F.text == QUEUE_BUTTON_TEXT)
async def handle_queue(
    message: Message,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return
    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)
    await state.clear()

    async with helpdesk_service_factory() as helpdesk_service:
        queued_tickets = await helpdesk_service.list_queued_tickets(
            actor_telegram_user_id=message.from_user.id if message.from_user is not None else None,
        )

    if not queued_tickets:
        await message.answer(QUEUE_EMPTY_TEXT)
        return

    queue_text, queue_markup = _build_queue_page_response(queued_tickets=queued_tickets, page=1)
    await message.answer(queue_text, reply_markup=queue_markup)


@router.message(F.text == MY_TICKETS_BUTTON_TEXT)
async def handle_my_tickets(
    message: Message,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if message.from_user is None:
        await message.answer(OPERATOR_UNKNOWN_TEXT)
        return
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=message.from_user.id)
    await state.clear()
    async with helpdesk_service_factory() as helpdesk_service:
        tickets = await helpdesk_service.list_operator_tickets(
            operator_telegram_user_id=message.from_user.id,
            actor_telegram_user_id=message.from_user.id,
        )

    if not tickets:
        await message.answer(MY_TICKETS_EMPTY_TEXT)
        return

    tickets_text, tickets_markup = _build_my_tickets_page_response(tickets=tickets, page=1)
    await message.answer(tickets_text, reply_markup=tickets_markup)


@router.callback_query(OperatorQueueCallback.filter(F.action == "page"))
async def handle_ticket_index_page(
    callback: CallbackQuery,
    callback_data: OperatorQueueCallback,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    await state.clear()

    if not isinstance(callback.message, Message):
        await callback.answer(build_queue_page_callback_text(callback_data.page))
        return

    if callback_data.scope == "mine":
        async with helpdesk_service_factory() as helpdesk_service:
            tickets = await helpdesk_service.list_operator_tickets(
                operator_telegram_user_id=callback.from_user.id,
                actor_telegram_user_id=callback.from_user.id,
            )
        if not tickets:
            await callback.answer(MY_TICKETS_EMPTY_TEXT)
            await callback.message.edit_text(MY_TICKETS_EMPTY_TEXT, reply_markup=None)
            return

        tickets_text, tickets_markup = _build_my_tickets_page_response(
            tickets=tickets,
            page=callback_data.page,
        )
        await callback.answer()
        await callback.message.edit_text(tickets_text, reply_markup=tickets_markup)
        return

    async with helpdesk_service_factory() as helpdesk_service:
        queued_tickets = await helpdesk_service.list_queued_tickets(
            actor_telegram_user_id=callback.from_user.id,
        )

    if not queued_tickets:
        await callback.answer(QUEUE_EMPTY_TEXT)
        await callback.message.edit_text(QUEUE_EMPTY_TEXT, reply_markup=None)
        return

    queue_text, queue_markup = _build_queue_page_response(
        queued_tickets=queued_tickets,
        page=callback_data.page,
    )
    await callback.answer()
    await callback.message.edit_text(queue_text, reply_markup=queue_markup)


@router.callback_query(OperatorQueueCallback.filter(F.action == "noop"))
async def handle_queue_page_noop(
    callback: CallbackQuery,
    callback_data: OperatorQueueCallback,
) -> None:
    await callback.answer(build_queue_page_callback_text(callback_data.page))


@router.message(F.text == TAKE_NEXT_BUTTON_TEXT)
async def handle_take_next(
    message: Message,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_lock_manager: TicketLockManager,
) -> None:
    from bot.formatters.operator import format_status
    from bot.handlers.operator.workflow_ticket_actions import send_ticket_details
    from bot.texts.operator import build_take_next_fallback_text

    if message.from_user is None:
        await message.answer(OPERATOR_UNKNOWN_TEXT)
        return
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=message.from_user.id)
    await state.clear()

    queue_lock = ticket_lock_manager.for_ticket("queue-next")
    if not await queue_lock.acquire():
        await message.answer(QUEUE_BUSY_TEXT)
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            ticket = await helpdesk_service.assign_next_ticket_to_operator(
                telegram_user_id=message.from_user.id,
                display_name=message.from_user.full_name,
                username=message.from_user.username,
                actor_telegram_user_id=message.from_user.id,
            )
            ticket_details = None
            if ticket is not None:
                ticket_details = await helpdesk_service.get_ticket_details(
                    ticket_public_id=ticket.public_id,
                    actor_telegram_user_id=message.from_user.id,
                )
    finally:
        await queue_lock.release()

    if ticket is None:
        await message.answer(NO_QUEUE_TICKETS_TEXT)
        return
    if ticket_details is None:
        await message.answer(
            build_take_next_fallback_text(ticket.public_number, format_status(ticket.status))
        )
        return

    logger.info(
        "Operator took next queued ticket operator_id=%s ticket=%s",
        message.from_user.id,
        ticket.public_number,
    )
    await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=message.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )
    await send_ticket_details(
        message=message,
        ticket_details=ticket_details,
        include_history=True,
        is_active_context=True,
    )


async def _restore_ticket_after_cancel(
    *,
    message: Message,
    state_data: dict[str, object],
    helpdesk_service_factory: HelpdeskServiceFactory,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
) -> None:
    from bot.handlers.operator.workflow_ticket_actions import send_ticket_details

    ticket_public_id_value = state_data.get("ticket_public_id")
    ticket_public_id = parse_ticket_public_id(
        ticket_public_id_value if isinstance(ticket_public_id_value, str) else None
    )
    if ticket_public_id is None or message.from_user is None:
        return

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor_telegram_user_id=message.from_user.id,
        )

    if ticket_details is None:
        return

    is_active_context = await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=message.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )
    await send_ticket_details(
        message=message,
        ticket_details=ticket_details,
        is_active_context=is_active_context,
    )


async def _restore_operator_directory_after_cancel(
    *,
    message: Message,
    settings: Settings,
    helpdesk_service_factory: HelpdeskServiceFactory,
) -> None:
    if message.from_user is None:
        return

    async with helpdesk_service_factory() as helpdesk_service:
        operators = await helpdesk_service.list_operators(
            actor_telegram_user_id=message.from_user.id,
        )

    await message.answer(
        format_operator_list_response(
            operators=operators,
            super_admin_telegram_user_ids=settings.authorization.super_admin_telegram_user_ids,
        ),
        reply_markup=build_operator_management_markup(operators=operators),
    )


async def _restore_macro_list_after_cancel(
    *,
    message: Message,
    state_data: dict[str, object],
    helpdesk_service_factory: HelpdeskServiceFactory,
) -> None:
    if message.from_user is None:
        return

    page = _parse_page(state_data.get("page"))
    async with helpdesk_service_factory() as helpdesk_service:
        macros = await helpdesk_service.list_macros(actor_telegram_user_id=message.from_user.id)

    text, markup = _build_admin_macro_list_response(macros=macros, page=page)
    await message.answer(text, reply_markup=markup)


async def _restore_macro_details_after_cancel(
    *,
    message: Message,
    state_data: dict[str, object],
    helpdesk_service_factory: HelpdeskServiceFactory,
) -> None:
    if message.from_user is None:
        return

    macro_id = state_data.get("macro_id")
    page = _parse_page(state_data.get("page"))
    if not isinstance(macro_id, int):
        await _restore_macro_list_after_cancel(
            message=message,
            state_data=state_data,
            helpdesk_service_factory=helpdesk_service_factory,
        )
        return

    async with helpdesk_service_factory() as helpdesk_service:
        macro = await helpdesk_service.get_macro(
            macro_id=macro_id,
            actor_telegram_user_id=message.from_user.id,
        )
        if macro is None:
            macros = await helpdesk_service.list_macros(actor_telegram_user_id=message.from_user.id)
            text, markup = _build_admin_macro_list_response(macros=macros, page=page)
            await message.answer(text, reply_markup=markup)
            return

    await message.answer(
        format_admin_macro_details(macro),
        reply_markup=build_admin_macro_detail_markup(
            macro_id=macro.id,
            page=page,
        ),
    )


def _build_admin_macro_list_response(
    *,
    macros: Sequence[MacroSummary],
    page: int,
) -> tuple[str, InlineKeyboardMarkup]:
    page_macros, current_page, total_pages = paginate_macros(macros, page=page)
    return (
        format_admin_macro_list(
            page_macros,
            current_page=current_page,
            total_pages=total_pages,
        ),
        build_admin_macro_list_markup(
            macros=page_macros,
            current_page=current_page,
            total_pages=total_pages,
        ),
    )


def _parse_page(value: object) -> int:
    return value if isinstance(value, int) and value > 0 else 1


def _build_queue_page_response(
    *,
    queued_tickets: Sequence[QueuedTicketSummary],
    page: int,
) -> tuple[str, InlineKeyboardMarkup]:
    total_pages = max(1, ceil(len(queued_tickets) / QUEUE_PAGE_SIZE))
    safe_page = min(max(page, 1), total_pages)
    start = (safe_page - 1) * QUEUE_PAGE_SIZE
    end = start + QUEUE_PAGE_SIZE
    page_tickets = queued_tickets[start:end]
    return (
        format_queue_page(page_tickets, current_page=safe_page, total_pages=total_pages),
        build_queue_markup(
            tickets=page_tickets,
            current_page=safe_page,
            total_pages=total_pages,
        ),
    )


def _build_my_tickets_page_response(
    *,
    tickets: Sequence[OperatorTicketSummary],
    page: int,
) -> tuple[str, InlineKeyboardMarkup]:
    total_pages = max(1, ceil(len(tickets) / QUEUE_PAGE_SIZE))
    safe_page = min(max(page, 1), total_pages)
    start = (safe_page - 1) * QUEUE_PAGE_SIZE
    end = start + QUEUE_PAGE_SIZE
    page_tickets = tickets[start:end]
    return (
        format_operator_ticket_page(page_tickets, current_page=safe_page, total_pages=total_pages),
        build_operator_ticket_list_markup(
            tickets=page_tickets,
            current_page=safe_page,
            total_pages=total_pages,
        ),
    )
