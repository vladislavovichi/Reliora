from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import MagicData, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.callbacks import ClientTicketCallback
from bot.delivery import deliver_ticket_closed_to_operator
from bot.handlers.common.ticket_attachments import extract_ticket_content
from bot.handlers.operator.active_context import delete_live_session_for_ticket
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.handlers.user.intake import start_client_intake
from bot.handlers.user.workflow import process_client_ticket_message
from bot.keyboards.inline.client_actions import (
    build_client_ticket_finish_confirmation_markup,
    build_client_ticket_markup,
)
from bot.keyboards.inline.feedback import build_ticket_feedback_rating_markup
from bot.keyboards.inline.operator_actions import build_ticket_switch_markup
from bot.texts.client import (
    FINISH_TICKET_CANCELLED_TEXT,
    FINISH_TICKET_LOCKED_TEXT,
    FINISH_TICKET_STALE_TEXT,
    build_finish_ticket_prompt_text,
    build_ticket_already_closed_text,
    build_ticket_closed_text,
)
from bot.texts.common import CHAT_RATE_LIMIT_TEXT, SERVICE_UNAVAILABLE_TEXT
from bot.texts.feedback import build_ticket_closed_with_feedback_text
from domain.enums.roles import UserRole
from domain.enums.tickets import TicketStatus
from domain.tickets import InvalidTicketTransitionError
from infrastructure.redis.contracts import (
    ChatRateLimiter,
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    TicketLiveSessionStore,
    TicketLockManager,
    TicketStreamPublisher,
)

router = Router(name="client")
logger = logging.getLogger(__name__)
SUPPORTED_TICKET_MEDIA_FILTER = F.photo | F.document | F.voice | F.video


@router.message(
    StateFilter(None),
    MagicData(F.event_user_role == UserRole.USER),
    F.text & ~F.text.startswith("/"),
)
@router.message(
    StateFilter(None),
    MagicData(F.event_user_role == UserRole.USER),
    SUPPORTED_TICKET_MEDIA_FILTER,
)
async def handle_client_text(
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

    content = await extract_ticket_content(message, bot=bot)
    if content is None:
        return

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        active_ticket = await helpdesk_backend.get_client_active_ticket(
            client_chat_id=message.chat.id
        )
        if active_ticket is None:
            categories = await helpdesk_backend.list_client_ticket_categories()
            if categories:
                await start_client_intake(
                    message=message,
                    state=state,
                    categories=categories,
                    content=content,
                )
                return

    await process_client_ticket_message(
        message=message,
        bot=bot,
        helpdesk_backend_client_factory=helpdesk_backend_client_factory,
        operator_active_ticket_store=operator_active_ticket_store,
        ticket_live_session_store=ticket_live_session_store,
        ticket_stream_publisher=ticket_stream_publisher,
        logger=logger,
        content=content,
    )


@router.callback_query(
    MagicData(F.event_user_role == UserRole.USER),
    ClientTicketCallback.filter(F.action == "finish"),
)
async def handle_finish_ticket_prompt(
    callback: CallbackQuery,
    callback_data: ClientTicketCallback,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
) -> None:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await callback.answer(FINISH_TICKET_STALE_TEXT, show_alert=True)
        return
    if not await global_rate_limiter.allow():
        await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
        return

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        ticket_details = await helpdesk_backend.get_ticket_details(
            ticket_public_id=ticket_public_id
        )

    if ticket_details is None:
        await callback.answer(FINISH_TICKET_STALE_TEXT, show_alert=True)
        return
    if ticket_details.status == TicketStatus.CLOSED:
        await callback.answer(
            build_ticket_already_closed_text(ticket_details.public_number),
            show_alert=True,
        )
        return

    if not await _try_edit_client_ticket_markup(
        callback=callback,
        reply_markup=build_client_ticket_finish_confirmation_markup(
            ticket_public_id=ticket_public_id
        ),
    ):
        await callback.answer(FINISH_TICKET_STALE_TEXT, show_alert=True)
        return

    await callback.answer(build_finish_ticket_prompt_text(ticket_details.public_number))


@router.callback_query(
    MagicData(F.event_user_role == UserRole.USER),
    ClientTicketCallback.filter(F.action == "finish_cancel"),
)
async def handle_finish_ticket_cancel(
    callback: CallbackQuery,
    callback_data: ClientTicketCallback,
) -> None:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await callback.answer(FINISH_TICKET_STALE_TEXT, show_alert=True)
        return

    if not await _try_edit_client_ticket_markup(
        callback=callback,
        reply_markup=build_client_ticket_markup(ticket_public_id=ticket_public_id),
    ):
        await callback.answer(FINISH_TICKET_STALE_TEXT, show_alert=True)
        return

    await callback.answer(FINISH_TICKET_CANCELLED_TEXT)


@router.callback_query(
    MagicData(F.event_user_role == UserRole.USER),
    ClientTicketCallback.filter(F.action == "finish_confirm"),
)
async def handle_finish_ticket_confirm(
    callback: CallbackQuery,
    callback_data: ClientTicketCallback,
    bot: Bot,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_lock_manager: TicketLockManager,
) -> None:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await callback.answer(FINISH_TICKET_STALE_TEXT, show_alert=True)
        return
    if not await global_rate_limiter.allow():
        await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
        return

    lock = ticket_lock_manager.for_ticket(str(ticket_public_id))
    if not await lock.acquire():
        await callback.answer(FINISH_TICKET_LOCKED_TEXT, show_alert=True)
        return

    closed_ticket = None
    ticket_details = None
    try:
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            ticket_details = await helpdesk_backend.get_ticket_details(
                ticket_public_id=ticket_public_id
            )
            if ticket_details is None:
                await callback.answer(FINISH_TICKET_STALE_TEXT, show_alert=True)
                return
            if ticket_details.status == TicketStatus.CLOSED:
                await callback.answer(
                    build_ticket_already_closed_text(ticket_details.public_number),
                    show_alert=True,
                )
                return

            try:
                closed_ticket = await helpdesk_backend.close_ticket(
                    ticket_public_id=ticket_public_id
                )
            except InvalidTicketTransitionError:
                refreshed_ticket_details = await helpdesk_backend.get_ticket_details(
                    ticket_public_id=ticket_public_id
                )
                if (
                    refreshed_ticket_details is not None
                    and refreshed_ticket_details.status == TicketStatus.CLOSED
                ):
                    await callback.answer(
                        build_ticket_already_closed_text(refreshed_ticket_details.public_number),
                        show_alert=True,
                    )
                    return
                await callback.answer(FINISH_TICKET_STALE_TEXT, show_alert=True)
                return
    finally:
        await lock.release()

    if closed_ticket is None or ticket_details is None:
        await callback.answer(FINISH_TICKET_STALE_TEXT, show_alert=True)
        return

    await delete_live_session_for_ticket(
        ticket_live_session_store=ticket_live_session_store,
        ticket_public_id=str(ticket_public_id),
    )

    if ticket_details.assigned_operator_telegram_user_id is not None:
        await operator_active_ticket_store.clear_if_matches(
            operator_id=ticket_details.assigned_operator_telegram_user_id,
            ticket_public_id=str(ticket_public_id),
        )
        delivery_error = await deliver_ticket_closed_to_operator(
            bot,
            chat_id=ticket_details.assigned_operator_telegram_user_id,
            public_number=ticket_details.public_number,
            reply_markup=build_ticket_switch_markup(ticket_public_id=ticket_public_id),
            logger=logger,
        )
        if delivery_error is not None:
            logger.warning(
                "Failed to notify operator about client-side closure "
                "ticket=%s operator_chat_id=%s error=%s",
                ticket_details.public_number,
                ticket_details.assigned_operator_telegram_user_id,
                delivery_error,
            )

    await _try_edit_client_ticket_markup(callback=callback, reply_markup=None)
    if isinstance(callback.message, Message):
        await callback.message.answer(
            build_ticket_closed_with_feedback_text(ticket_details.public_number),
            reply_markup=build_ticket_feedback_rating_markup(ticket_public_id=ticket_public_id),
        )
        await callback.answer()
        return

    await callback.answer(build_ticket_closed_text(ticket_details.public_number), show_alert=True)


async def _try_edit_client_ticket_markup(
    *,
    callback: CallbackQuery,
    reply_markup: InlineKeyboardMarkup | None,
) -> bool:
    if not isinstance(callback.message, Message):
        return False

    try:
        await callback.message.edit_reply_markup(reply_markup=reply_markup)
    except TelegramBadRequest:
        return False
    return True
