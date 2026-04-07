from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.summaries import TicketDetailsSummary
from bot.callbacks import OperatorActionCallback
from bot.delivery import deliver_ticket_closed_to_client
from bot.formatters.operator import format_ticket_details, format_ticket_history_chunks
from bot.handlers.operator.common import operator_ticket_action, respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.keyboards.inline.operator_actions import build_ticket_actions_markup
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.operator import (
    build_close_delivery_failed_text,
    build_close_text,
    build_escalate_text,
    build_take_answer_text,
    build_view_opened_text,
)
from domain.enums.tickets import TicketEventType
from domain.tickets import InvalidTicketTransitionError
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorPresenceHelper,
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

    await callback.answer(build_view_opened_text(ticket_details.public_number))
    if callback.message is None:
        return

    await callback.message.answer(
        format_ticket_details(ticket_details),
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

    await _answer_with_ticket_details(
        callback=callback,
        ticket_details=ticket_details,
        fallback_text=build_take_answer_text(
            ticket.public_number,
            reassigned=ticket.event_type == TicketEventType.REASSIGNED,
        ),
        include_history=True,
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "close"))
async def handle_close_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
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

    await _answer_with_ticket_details(
        callback=callback,
        ticket_details=ticket_details,
        fallback_text=build_escalate_text(ticket.public_number),
    )


async def _answer_with_ticket_details(
    *,
    callback: CallbackQuery,
    ticket_details: TicketDetailsSummary | None,
    fallback_text: str,
    include_history: bool = False,
) -> None:
    if callback.message is None or ticket_details is None:
        await respond_to_operator(callback, fallback_text)
        return

    await callback.answer(fallback_text)
    await callback.message.answer(
        format_ticket_details(ticket_details),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )
    if not include_history:
        return

    for chunk in format_ticket_history_chunks(ticket_details):
        await callback.message.answer(chunk)
