from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.summaries import TicketDetailsSummary
from bot.callbacks import OperatorActionCallback
from bot.delivery import deliver_ticket_closed_to_client
from bot.formatters.operator import (
    format_active_ticket_context,
    format_ticket_details,
    format_ticket_history_chunks,
    format_ticket_more_actions,
)
from bot.handlers.operator.active_context import (
    activate_ticket_for_operator,
    clear_active_ticket_for_operator,
    delete_live_session_for_ticket,
)
from bot.handlers.operator.common import operator_ticket_action, respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.keyboards.inline.operator_actions import (
    build_ticket_actions_markup,
    build_ticket_more_actions_markup,
)
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.operator import (
    build_active_ticket_opened_text,
    build_close_delivery_failed_text,
    build_close_text,
    build_escalate_text,
    build_more_actions_opened_text,
    build_take_answer_text,
    build_view_opened_text,
)
from domain.enums.tickets import TicketEventType
from domain.tickets import InvalidTicketTransitionError
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    TicketLiveSessionStore,
    TicketLockManager,
)

router = Router(name="operator_workflow_ticket_actions")
logger = logging.getLogger(__name__)


@router.callback_query(OperatorActionCallback.filter(F.action == "view"))
async def handle_view_action(
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

    is_active_context = await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )

    await _answer_with_ticket_details(
        callback=callback,
        ticket_details=ticket_details,
        fallback_text=(
            build_active_ticket_opened_text(ticket_details.public_number)
            if is_active_context
            else build_view_opened_text(ticket_details.public_number)
        ),
        include_history=is_active_context,
        is_active_context=is_active_context,
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "card"))
async def handle_card_action(
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

    is_active_context = await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )

    if not isinstance(callback.message, Message):
        await callback.answer(build_view_opened_text(ticket_details.public_number))
        return

    await callback.answer(build_view_opened_text(ticket_details.public_number))
    await callback.message.edit_text(
        format_ticket_details(ticket_details, is_active=is_active_context),
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
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
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

    is_active_context = False
    if ticket_details is not None:
        is_active_context = await activate_ticket_for_operator(
            active_ticket_store=operator_active_ticket_store,
            operator_telegram_user_id=callback.from_user.id,
            ticket_details=ticket_details,
            ticket_live_session_store=ticket_live_session_store,
        )

    await _answer_with_ticket_details(
        callback=callback,
        ticket_details=ticket_details,
        fallback_text=build_take_answer_text(
            ticket.public_number,
            reassigned=ticket.event_type == TicketEventType.REASSIGNED,
        ),
        include_history=True,
        is_active_context=is_active_context,
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "close"))
async def handle_close_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
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

    await clear_active_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_public_id=str(ticket.public_id),
    )
    await delete_live_session_for_ticket(
        ticket_live_session_store=ticket_live_session_store,
        ticket_public_id=str(ticket.public_id),
    )

    delivery_error: str | None = None
    if ticket_details is not None:
        delivery_error = await deliver_ticket_closed_to_client(
            bot,
            chat_id=ticket_details.client_chat_id,
            public_number=ticket.public_number,
            logger=logger,
        )

    await _answer_with_ticket_details(
        callback=callback,
        ticket_details=ticket_details,
        fallback_text=(
            build_close_text(ticket.public_number)
            if delivery_error is None
            else build_close_delivery_failed_text(ticket.public_number, delivery_error)
        ),
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "escalate"))
async def handle_escalate_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
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

    is_active_context = False
    if ticket_details is not None:
        is_active_context = await activate_ticket_for_operator(
            active_ticket_store=operator_active_ticket_store,
            operator_telegram_user_id=callback.from_user.id,
            ticket_details=ticket_details,
            ticket_live_session_store=ticket_live_session_store,
        )

    await _answer_with_ticket_details(
        callback=callback,
        ticket_details=ticket_details,
        fallback_text=build_escalate_text(ticket.public_number),
        is_active_context=is_active_context,
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "more"))
async def handle_more_action(
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

    is_active_context = await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )

    if not isinstance(callback.message, Message):
        await callback.answer(build_more_actions_opened_text(ticket_details.public_number))
        return

    await callback.answer(build_more_actions_opened_text(ticket_details.public_number))
    await callback.message.edit_text(
        format_ticket_more_actions(ticket_details, is_active=is_active_context),
        reply_markup=build_ticket_more_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


async def _answer_with_ticket_details(
    *,
    callback: CallbackQuery,
    ticket_details: TicketDetailsSummary | None,
    fallback_text: str,
    include_history: bool = False,
    is_active_context: bool = False,
) -> None:
    if not isinstance(callback.message, Message) or ticket_details is None:
        await respond_to_operator(callback, fallback_text)
        return

    await callback.answer(fallback_text)
    await send_ticket_details(
        message=callback.message,
        ticket_details=ticket_details,
        include_history=include_history,
        is_active_context=is_active_context,
    )


async def send_ticket_details(
    *,
    message: Message,
    ticket_details: TicketDetailsSummary,
    include_history: bool = False,
    is_active_context: bool = False,
) -> None:
    await message.answer(
        (
            format_active_ticket_context(ticket_details)
            if is_active_context
            else format_ticket_details(ticket_details)
        ),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )
    if not include_history:
        return

    for chunk in format_ticket_history_chunks(ticket_details):
        await message.answer(chunk)
