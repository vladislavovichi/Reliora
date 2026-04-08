from __future__ import annotations

import logging
from collections.abc import Sequence

from aiogram import Bot, F, Router
from aiogram.filters import MagicData, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.summaries import TicketCategorySummary
from bot.callbacks import ClientIntakeCallback
from bot.handlers.user.states import UserIntakeStates
from bot.handlers.user.workflow import process_client_ticket_message
from bot.keyboards.inline.categories import (
    build_client_intake_categories_markup,
    build_client_intake_message_markup,
)
from bot.texts.categories import (
    INTAKE_CANCELLED_TEXT,
    INTAKE_CATEGORY_PROMPT_TEXT,
    INTAKE_CATEGORY_STALE_TEXT,
    build_intake_message_prompt_text,
)
from bot.texts.common import CHAT_RATE_LIMIT_TEXT, SERVICE_UNAVAILABLE_TEXT
from domain.enums.roles import UserRole
from infrastructure.redis.contracts import (
    ChatRateLimiter,
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    TicketLiveSessionStore,
    TicketStreamPublisher,
)

router = Router(name="client_intake")
logger = logging.getLogger(__name__)


async def start_client_intake(
    *,
    message: Message,
    state: FSMContext,
    categories: Sequence[TicketCategorySummary],
) -> None:
    await state.set_state(UserIntakeStates.choosing_category)
    await message.answer(
        INTAKE_CATEGORY_PROMPT_TEXT,
        reply_markup=build_client_intake_categories_markup(categories),
    )


@router.callback_query(
    MagicData(F.event_user_role == UserRole.USER),
    ClientIntakeCallback.filter(F.action == "pick"),
)
async def handle_client_intake_category_pick(
    callback: CallbackQuery,
    callback_data: ClientIntakeCallback,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
) -> None:
    if await state.get_state() != UserIntakeStates.choosing_category.state:
        await callback.answer(INTAKE_CATEGORY_STALE_TEXT, show_alert=True)
        return
    if not await global_rate_limiter.allow():
        await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
        return

    async with helpdesk_service_factory() as helpdesk_service:
        categories = await helpdesk_service.list_client_ticket_categories()

    category = next((item for item in categories if item.id == callback_data.category_id), None)
    if category is None:
        await callback.answer(INTAKE_CATEGORY_STALE_TEXT, show_alert=True)
        return

    await state.set_state(UserIntakeStates.writing_message)
    await state.set_data({"category_id": category.id, "category_title": category.title})
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            build_intake_message_prompt_text(category.title),
            reply_markup=build_client_intake_message_markup(),
        )


@router.callback_query(
    MagicData(F.event_user_role == UserRole.USER),
    ClientIntakeCallback.filter(F.action == "cancel"),
)
async def handle_client_intake_cancel(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(INTAKE_CANCELLED_TEXT, reply_markup=None)


@router.message(
    StateFilter(UserIntakeStates.writing_message),
    MagicData(F.event_user_role == UserRole.USER),
    F.text & ~F.text.startswith("/"),
)
async def handle_client_intake_message(
    message: Message,
    state: FSMContext,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    chat_rate_limiter: ChatRateLimiter,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_stream_publisher: TicketStreamPublisher,
) -> None:
    if message.text is None:
        return
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return
    if not await chat_rate_limiter.allow(chat_id=message.chat.id):
        await message.answer(CHAT_RATE_LIMIT_TEXT)
        return

    state_data = await state.get_data()
    category_id = state_data.get("category_id")
    if not isinstance(category_id, int):
        await state.clear()
        await message.answer(INTAKE_CATEGORY_STALE_TEXT)
        return

    await state.clear()
    await process_client_ticket_message(
        message=message,
        bot=bot,
        helpdesk_service_factory=helpdesk_service_factory,
        operator_active_ticket_store=operator_active_ticket_store,
        ticket_live_session_store=ticket_live_session_store,
        ticket_stream_publisher=ticket_stream_publisher,
        logger=logger,
        category_id=category_id,
    )
