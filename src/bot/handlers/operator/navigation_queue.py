from __future__ import annotations

import logging
from collections.abc import Sequence
from math import ceil

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from application.use_cases.tickets.summaries import OperatorTicketSummary, QueuedTicketSummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import (
    build_assign_next_ticket_command,
    build_operator_identity,
    build_request_actor,
)
from bot.callbacks import OperatorQueueCallback
from bot.formatters.operator_primitives import format_status
from bot.formatters.operator_ticket_views import format_operator_ticket_page, format_queue_page
from bot.handlers.operator.active_context import activate_ticket_for_operator
from bot.handlers.operator.ticket_surfaces import send_ticket_details
from bot.keyboards.inline.operator_actions import (
    build_operator_ticket_list_markup,
    build_queue_markup,
)
from bot.texts.buttons import MY_TICKETS_BUTTON_TEXT, QUEUE_BUTTON_TEXT, TAKE_NEXT_BUTTON_TEXT
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from bot.texts.operator import (
    MY_TICKETS_EMPTY_TEXT,
    NO_QUEUE_TICKETS_TEXT,
    OPERATOR_UNKNOWN_TEXT,
    QUEUE_BUSY_TEXT,
    QUEUE_EMPTY_TEXT,
    build_queue_page_callback_text,
    build_take_next_fallback_text,
)
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    TicketLiveSessionStore,
    TicketLockManager,
)

QUEUE_PAGE_SIZE = 5

router = Router(name="operator_navigation_queue")
logger = logging.getLogger(__name__)


@router.message(F.text == QUEUE_BUTTON_TEXT)
async def handle_queue(
    message: Message,
    state: FSMContext,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return
    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)
    await state.clear()

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        queued_tickets = await helpdesk_backend.list_queued_tickets(
            actor=build_request_actor(message.from_user),
        )

    if not queued_tickets:
        await message.answer(QUEUE_EMPTY_TEXT)
        return

    queue_text, queue_markup = build_queue_page_response(queued_tickets=queued_tickets, page=1)
    await message.answer(queue_text, reply_markup=queue_markup)


@router.message(F.text == MY_TICKETS_BUTTON_TEXT)
async def handle_my_tickets(
    message: Message,
    state: FSMContext,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
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
    async with helpdesk_backend_client_factory() as helpdesk_backend:
        tickets = await helpdesk_backend.list_operator_tickets(
            operator_telegram_user_id=message.from_user.id,
            actor=build_request_actor(message.from_user),
        )

    if not tickets:
        await message.answer(MY_TICKETS_EMPTY_TEXT)
        return

    tickets_text, tickets_markup = build_my_tickets_page_response(tickets=tickets, page=1)
    await message.answer(tickets_text, reply_markup=tickets_markup)


@router.callback_query(OperatorQueueCallback.filter(F.action == "page"))
async def handle_ticket_index_page(
    callback: CallbackQuery,
    callback_data: OperatorQueueCallback,
    state: FSMContext,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
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
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            tickets = await helpdesk_backend.list_operator_tickets(
                operator_telegram_user_id=callback.from_user.id,
                actor=build_request_actor(callback.from_user),
            )
        if not tickets:
            await callback.answer(MY_TICKETS_EMPTY_TEXT)
            await callback.message.edit_text(MY_TICKETS_EMPTY_TEXT, reply_markup=None)
            return

        tickets_text, tickets_markup = build_my_tickets_page_response(
            tickets=tickets,
            page=callback_data.page,
        )
        await callback.answer()
        await callback.message.edit_text(tickets_text, reply_markup=tickets_markup)
        return

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        queued_tickets = await helpdesk_backend.list_queued_tickets(
            actor=build_request_actor(callback.from_user),
        )

    if not queued_tickets:
        await callback.answer(QUEUE_EMPTY_TEXT)
        await callback.message.edit_text(QUEUE_EMPTY_TEXT, reply_markup=None)
        return

    queue_text, queue_markup = build_queue_page_response(
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
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_lock_manager: TicketLockManager,
) -> None:
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
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            operator = build_operator_identity(message.from_user)
            if operator is None:
                await message.answer(OPERATOR_UNKNOWN_TEXT)
                return
            ticket = await helpdesk_backend.assign_next_ticket_to_operator(
                build_assign_next_ticket_command(operator=operator),
                actor=build_request_actor(message.from_user),
            )
            ticket_details = None
            if ticket is not None:
                ticket_details = await helpdesk_backend.get_ticket_details(
                    ticket_public_id=ticket.public_id,
                    actor=build_request_actor(message.from_user),
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


def build_queue_page_response(
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


def build_my_tickets_page_response(
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
