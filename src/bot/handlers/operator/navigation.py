from __future__ import annotations

import logging
from collections.abc import Sequence
from math import ceil

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.summaries import OperatorTicketSummary, QueuedTicketSummary
from bot.callbacks import OperatorQueueCallback
from bot.formatters.operator import (
    QUEUE_PAGE_SIZE,
    format_operator_ticket_page,
    format_queue_page,
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
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorPresenceHelper,
    TicketLockManager,
)

router = Router(name="operator_navigation")
logger = logging.getLogger(__name__)


@router.message(Command("cancel"))
@router.message(F.text == CANCEL_BUTTON_TEXT)
async def handle_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer(OPERATOR_ACTION_IDLE_TEXT)
        return

    await state.clear()
    await message.answer(OPERATOR_ACTION_CANCELLED_TEXT)


@router.message(Command("queue"))
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


@router.message(Command("take"))
@router.message(F.text == TAKE_NEXT_BUTTON_TEXT)
async def handle_take_next(
    message: Message,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
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
    await send_ticket_details(
        message=message,
        ticket_details=ticket_details,
        include_history=True,
    )


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
