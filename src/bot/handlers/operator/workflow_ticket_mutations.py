from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.summaries import TicketDetailsSummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import (
    build_operator_identity,
    build_request_actor,
    build_ticket_assignment_command,
)
from bot.callbacks import OperatorActionCallback
from bot.delivery import deliver_ticket_closed_to_client
from bot.handlers.operator.active_context import (
    activate_ticket_for_operator,
    clear_active_ticket_for_operator,
    delete_live_session_for_ticket,
)
from bot.handlers.operator.common import operator_ticket_action, respond_to_operator
from bot.handlers.operator.ticket_surfaces import send_ticket_details
from bot.keyboards.inline.feedback import build_ticket_feedback_rating_markup
from bot.texts.common import TICKET_NOT_FOUND_TEXT
from bot.texts.operator import (
    build_close_delivery_failed_text,
    build_close_text,
    build_escalate_text,
    build_take_answer_text,
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

router = Router(name="operator_workflow_ticket_mutations")
logger = logging.getLogger(__name__)


@router.callback_query(OperatorActionCallback.filter(F.action == "take"))
async def handle_take_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
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

        async with helpdesk_backend_client_factory() as helpdesk_backend:
            try:
                operator = build_operator_identity(callback.from_user)
                if operator is None:
                    await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
                    return
                ticket = await helpdesk_backend.assign_ticket_to_operator(
                    build_ticket_assignment_command(
                        ticket_public_id=ticket_public_id,
                        operator=operator,
                    ),
                    actor=build_request_actor(callback.from_user),
                )
                if ticket is not None:
                    ticket_details = await helpdesk_backend.get_ticket_details(
                        ticket_public_id=ticket.public_id,
                        actor=build_request_actor(callback.from_user),
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
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
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

        async with helpdesk_backend_client_factory() as helpdesk_backend:
            try:
                ticket = await helpdesk_backend.close_ticket_as_operator(
                    ticket_public_id=ticket_public_id,
                    actor=build_request_actor(callback.from_user),
                )
                if ticket is not None:
                    ticket_details = await helpdesk_backend.get_ticket_details(
                        ticket_public_id=ticket_public_id,
                        actor=build_request_actor(callback.from_user),
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
            reply_markup=build_ticket_feedback_rating_markup(ticket_public_id=ticket.public_id),
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
                    actor=build_request_actor(callback.from_user),
                )
                if ticket is not None:
                    ticket_details = await helpdesk_service.get_ticket_details(
                        ticket_public_id=ticket_public_id,
                        actor=build_request_actor(callback.from_user),
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
