from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import MagicData
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from bot.callbacks import ClientTicketCallback
from bot.delivery import deliver_client_message_to_operator, deliver_ticket_closed_to_operator
from bot.handlers.operator.active_context import delete_live_session_for_ticket
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.keyboards.inline.client_actions import (
    build_client_ticket_finish_confirmation_markup,
    build_client_ticket_markup,
)
from bot.keyboards.inline.operator_actions import build_ticket_actions_markup, build_ticket_switch_markup
from bot.texts.client import (
    FINISH_TICKET_CANCELLED_TEXT,
    FINISH_TICKET_LOCKED_TEXT,
    build_finish_ticket_prompt_text,
    build_ticket_already_closed_text,
    build_ticket_closed_text,
    build_ticket_created_text,
    build_ticket_message_added_text,
)
from bot.texts.common import CHAT_RATE_LIMIT_TEXT, SERVICE_UNAVAILABLE_TEXT
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


@router.message(MagicData(F.event_user_role == UserRole.USER), F.text & ~F.text.startswith("/"))
async def handle_client_text(
    message: Message,
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

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            ticket = await helpdesk_service.create_ticket_from_client_message(
                client_chat_id=message.chat.id,
                telegram_message_id=message.message_id,
                text=message.text,
            )
            ticket_details = await helpdesk_service.get_ticket_details(
                ticket_public_id=ticket.public_id,
            )
    except InvalidTicketTransitionError as exc:
        await message.answer(str(exc))
        return

    if ticket_details is None:
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await ticket_live_session_store.refresh_session(
        ticket_public_id=str(ticket.public_id),
        client_chat_id=message.chat.id,
        operator_telegram_user_id=ticket_details.assigned_operator_telegram_user_id,
    )

    logger.info(
        "Client ticket message processed client_chat_id=%s ticket=%s created=%s",
        message.chat.id,
        ticket.public_number,
        ticket.created,
    )

    if ticket.created:
        await ticket_stream_publisher.publish_new_ticket(
            ticket_id=str(ticket.public_id),
            client_chat_id=message.chat.id,
            subject=message.text.strip()[:255] or "Обращение клиента",
        )
        await message.answer(
            build_ticket_created_text(ticket.public_number),
            reply_markup=build_client_ticket_markup(ticket_public_id=ticket.public_id),
        )
        return

    operator_connected = ticket_details.assigned_operator_telegram_user_id is not None
    if operator_connected:
        active_ticket_public_id = await operator_active_ticket_store.get_active_ticket(
            operator_id=ticket_details.assigned_operator_telegram_user_id
        )
        is_active_context = active_ticket_public_id == str(ticket.public_id)
        delivery_error = await deliver_client_message_to_operator(
            bot,
            chat_id=ticket_details.assigned_operator_telegram_user_id,
            public_number=ticket.public_number,
            body=message.text,
            reply_markup=(
                build_ticket_actions_markup(
                    ticket_public_id=ticket.public_id,
                    status=ticket_details.status,
                )
                if is_active_context
                else build_ticket_switch_markup(ticket_public_id=ticket.public_id)
            ),
            active_context=is_active_context,
            logger=logger,
        )
        if delivery_error is not None:
            logger.warning(
                "Failed to forward client message to operator "
                "ticket=%s operator_chat_id=%s error=%s",
                ticket.public_number,
                ticket_details.assigned_operator_telegram_user_id,
                delivery_error,
            )

    await message.answer(
        build_ticket_message_added_text(
            ticket.public_number,
            operator_connected=operator_connected,
        ),
        reply_markup=build_client_ticket_markup(ticket_public_id=ticket.public_id),
    )


@router.callback_query(
    MagicData(F.event_user_role == UserRole.USER),
    ClientTicketCallback.filter(F.action == "finish"),
)
async def handle_finish_ticket_prompt(
    callback: CallbackQuery,
    callback_data: ClientTicketCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
) -> None:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
        return
    if not await global_rate_limiter.allow():
        await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
        return

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(ticket_public_id=ticket_public_id)

    if ticket_details is None:
        await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
        return
    if ticket_details.status == TicketStatus.CLOSED:
        await callback.answer(
            build_ticket_already_closed_text(ticket_details.public_number),
            show_alert=True,
        )
        return

    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(
            reply_markup=build_client_ticket_finish_confirmation_markup(
                ticket_public_id=ticket_public_id
            )
        )
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
        await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
        return

    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(
            reply_markup=build_client_ticket_markup(ticket_public_id=ticket_public_id)
        )
    await callback.answer(FINISH_TICKET_CANCELLED_TEXT)


@router.callback_query(
    MagicData(F.event_user_role == UserRole.USER),
    ClientTicketCallback.filter(F.action == "finish_confirm"),
)
async def handle_finish_ticket_confirm(
    callback: CallbackQuery,
    callback_data: ClientTicketCallback,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_lock_manager: TicketLockManager,
) -> None:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
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
        async with helpdesk_service_factory() as helpdesk_service:
            ticket_details = await helpdesk_service.get_ticket_details(ticket_public_id=ticket_public_id)
            if ticket_details is None:
                await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
                return
            if ticket_details.status == TicketStatus.CLOSED:
                await callback.answer(
                    build_ticket_already_closed_text(ticket_details.public_number),
                    show_alert=True,
                )
                return

            closed_ticket = await helpdesk_service.close_ticket(ticket_public_id=ticket_public_id)
    finally:
        await lock.release()

    if closed_ticket is None or ticket_details is None:
        await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
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
                "Failed to notify operator about client-side closure ticket=%s operator_chat_id=%s error=%s",
                ticket_details.public_number,
                ticket_details.assigned_operator_telegram_user_id,
                delivery_error,
            )

    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(build_ticket_closed_text(ticket_details.public_number))
    await callback.answer()
