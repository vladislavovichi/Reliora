from __future__ import annotations

import logging
from collections.abc import Sequence

from aiogram import Bot, F, Router
from aiogram.filters import MagicData, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.use_cases.tickets.summaries import TicketCategorySummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import build_client_ticket_message_command_from_values
from bot.callbacks import ClientIntakeCallback
from bot.handlers.common.ticket_attachments import IncomingTicketContent, extract_ticket_content
from bot.handlers.user.intake_draft import (
    build_pending_client_intake_draft,
    load_pending_client_intake_draft,
    store_pending_client_intake_draft,
)
from bot.handlers.user.states import UserIntakeStates
from bot.handlers.user.workflow import process_client_ticket_command, process_client_ticket_message
from bot.keyboards.inline.categories import (
    build_client_intake_categories_markup,
    build_client_intake_message_markup,
)
from bot.texts.categories import (
    INTAKE_CANCELLED_TEXT,
    INTAKE_CATEGORY_PROMPT_TEXT,
    INTAKE_CATEGORY_STALE_TEXT,
    build_intake_attachment_prompt_text,
    build_intake_category_selected_text,
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
SUPPORTED_TICKET_MEDIA_FILTER = F.photo | F.document | F.voice | F.video


async def start_client_intake(
    *,
    message: Message,
    state: FSMContext,
    categories: Sequence[TicketCategorySummary],
    content: IncomingTicketContent,
) -> None:
    await state.set_state(UserIntakeStates.choosing_category)
    await store_pending_client_intake_draft(
        state=state,
        draft=build_pending_client_intake_draft(
            client_chat_id=message.chat.id,
            telegram_message_id=message.message_id,
            content=content,
        ),
    )
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
    bot: Bot,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_stream_publisher: TicketStreamPublisher,
) -> None:
    if await state.get_state() != UserIntakeStates.choosing_category.state:
        await callback.answer(INTAKE_CATEGORY_STALE_TEXT, show_alert=True)
        return
    if not await global_rate_limiter.allow():
        await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
        return

    state_data = await state.get_data()
    draft = load_pending_client_intake_draft(state_data)

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        categories = await helpdesk_backend.list_client_ticket_categories()

    category = next((item for item in categories if item.id == callback_data.category_id), None)
    if category is None:
        await callback.answer(INTAKE_CATEGORY_STALE_TEXT, show_alert=True)
        return

    await callback.answer()
    if draft is None:
        await state.clear()
        if isinstance(callback.message, Message):
            await callback.message.edit_text(INTAKE_CATEGORY_STALE_TEXT, reply_markup=None)
        return

    if isinstance(callback.message, Message) and draft.has_meaningful_text:
        await callback.message.edit_text(
            build_intake_category_selected_text(category.title),
            reply_markup=None,
        )
        await state.clear()
        await process_client_ticket_command(
            response_message=callback.message,
            bot=bot,
            helpdesk_backend_client_factory=helpdesk_backend_client_factory,
            operator_active_ticket_store=operator_active_ticket_store,
            ticket_live_session_store=ticket_live_session_store,
            ticket_stream_publisher=ticket_stream_publisher,
            logger=logger,
            command=build_client_ticket_message_command_from_values(
                client_chat_id=draft.client_chat_id,
                telegram_message_id=draft.telegram_message_id,
                text=draft.text,
                attachment=draft.attachment,
                category_id=category.id,
            ),
            content=draft.to_content(),
            category_id=category.id,
        )
        return

    await state.set_state(UserIntakeStates.writing_message)
    await store_pending_client_intake_draft(
        state=state,
        draft=draft,
        extra_data={
            "category_id": category.id,
            "category_title": category.title,
        },
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            (
                build_intake_attachment_prompt_text(category.title)
                if draft.attachment is not None
                else build_intake_message_prompt_text(category.title)
            ),
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
@router.message(
    StateFilter(UserIntakeStates.writing_message),
    MagicData(F.event_user_role == UserRole.USER),
    SUPPORTED_TICKET_MEDIA_FILTER,
)
async def handle_client_intake_message(
    message: Message,
    state: FSMContext,
    bot: Bot,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    chat_rate_limiter: ChatRateLimiter,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_stream_publisher: TicketStreamPublisher,
) -> None:
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

    draft = load_pending_client_intake_draft(state_data)
    current_content = await extract_ticket_content(message, bot=bot)
    if current_content is None:
        return

    if draft is not None and draft.attachment is not None and current_content.text is None:
        category_title = state_data.get("category_title")
        await message.answer(
            build_intake_attachment_prompt_text(category_title)
            if isinstance(category_title, str)
            else INTAKE_CATEGORY_STALE_TEXT
        )
        return

    await state.clear()
    await process_client_ticket_message(
        message=message,
        bot=bot,
        helpdesk_backend_client_factory=helpdesk_backend_client_factory,
        operator_active_ticket_store=operator_active_ticket_store,
        ticket_live_session_store=ticket_live_session_store,
        ticket_stream_publisher=ticket_stream_publisher,
        logger=logger,
        category_id=category_id,
        content=(
            current_content
            if draft is None or draft.attachment is None
            else IncomingTicketContent(
                text=current_content.text,
                attachment=draft.attachment,
            )
        ),
    )
