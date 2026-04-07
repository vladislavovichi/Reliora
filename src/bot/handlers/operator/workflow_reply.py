from __future__ import annotations

import logging
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.filters import MagicData, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.summaries import TicketDetailsSummary
from bot.callbacks import OperatorActionCallback
from bot.delivery import deliver_operator_reply_to_client
from bot.handlers.operator.active_context import (
    activate_ticket_for_operator,
    clear_active_ticket_for_operator,
    resolve_active_ticket_for_operator,
)
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.handlers.operator.states import OperatorTicketStates
from bot.handlers.operator.workflow_ticket_actions import send_ticket_details
from bot.keyboards.inline.client_actions import build_client_ticket_markup
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_LOCKED_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.operator import (
    ACTIVE_TICKET_REQUIRED_TEXT,
    ACTIVE_TICKET_UNAVAILABLE_TEXT,
    OPERATOR_UNKNOWN_TEXT,
    REPLY_CONTEXT_LOST_TEXT,
    build_active_ticket_opened_text,
    build_reply_delivery_failed_text,
)
from domain.enums.roles import UserRole
from domain.tickets import InvalidTicketTransitionError
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    TicketLiveSessionStore,
    TicketLockManager,
)

router = Router(name="operator_workflow_reply")
logger = logging.getLogger(__name__)


@router.callback_query(OperatorActionCallback.filter(F.action == "reply"))
async def handle_reply_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    state: FSMContext,
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

    await state.clear()
    is_active_context = await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )
    if not is_active_context:
        await respond_to_operator(callback, ACTIVE_TICKET_UNAVAILABLE_TEXT)
        return

    await callback.answer(build_active_ticket_opened_text(ticket_details.public_number))
    if callback.message is None:
        return

    await send_ticket_details(
        message=callback.message,
        ticket_details=ticket_details,
        is_active_context=True,
    )


@router.message(StateFilter(OperatorTicketStates.replying), F.text)
async def handle_legacy_reply_message(
    message: Message,
    state: FSMContext,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_lock_manager: TicketLockManager,
) -> None:
    state_data = await state.get_data()
    ticket_public_id = parse_ticket_public_id(state_data.get("ticket_public_id"))
    if ticket_public_id is None:
        await state.clear()
        await message.answer(REPLY_CONTEXT_LOST_TEXT)
        return

    try:
        await _handle_operator_message(
            message=message,
            bot=bot,
            helpdesk_service_factory=helpdesk_service_factory,
            global_rate_limiter=global_rate_limiter,
            operator_presence=operator_presence,
            operator_active_ticket_store=operator_active_ticket_store,
            ticket_live_session_store=ticket_live_session_store,
            ticket_lock_manager=ticket_lock_manager,
            explicit_ticket_public_id=ticket_public_id,
        )
    finally:
        await state.clear()


@router.message(
    MagicData(F.event_user_role.in_({UserRole.OPERATOR, UserRole.SUPER_ADMIN})),
    StateFilter(None),
    F.text & ~F.text.startswith("/"),
)
async def handle_operator_message(
    message: Message,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_lock_manager: TicketLockManager,
) -> None:
    await _handle_operator_message(
        message=message,
        bot=bot,
        helpdesk_service_factory=helpdesk_service_factory,
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
        operator_active_ticket_store=operator_active_ticket_store,
        ticket_live_session_store=ticket_live_session_store,
        ticket_lock_manager=ticket_lock_manager,
    )


async def _handle_operator_message(
    *,
    message: Message,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_lock_manager: TicketLockManager,
    explicit_ticket_public_id: UUID | None = None,
) -> None:
    if message.from_user is None or message.text is None:
        await message.answer(OPERATOR_UNKNOWN_TEXT)
        return
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=message.from_user.id)

    ticket_details = await _resolve_target_ticket(
        message=message,
        helpdesk_service_factory=helpdesk_service_factory,
        operator_active_ticket_store=operator_active_ticket_store,
        explicit_ticket_public_id=explicit_ticket_public_id,
    )
    if ticket_details is None:
        await message.answer(
            REPLY_CONTEXT_LOST_TEXT if explicit_ticket_public_id is not None else ACTIVE_TICKET_REQUIRED_TEXT
        )
        return

    await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=message.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )

    lock = ticket_lock_manager.for_ticket(str(ticket_details.public_id))
    if not await lock.acquire():
        await message.answer(TICKET_LOCKED_TEXT)
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            try:
                reply_result = await helpdesk_service.reply_to_ticket_as_operator(
                    ticket_public_id=ticket_details.public_id,
                    telegram_user_id=message.from_user.id,
                    display_name=message.from_user.full_name,
                    username=message.from_user.username,
                    telegram_message_id=message.message_id,
                    text=message.text,
                    actor_telegram_user_id=message.from_user.id,
                )
            except InvalidTicketTransitionError as exc:
                await clear_active_ticket_for_operator(
                    active_ticket_store=operator_active_ticket_store,
                    operator_telegram_user_id=message.from_user.id,
                    ticket_public_id=str(ticket_details.public_id),
                )
                await message.answer(str(exc))
                return
    finally:
        await lock.release()

    if reply_result is None:
        await clear_active_ticket_for_operator(
            active_ticket_store=operator_active_ticket_store,
            operator_telegram_user_id=message.from_user.id,
            ticket_public_id=str(ticket_details.public_id),
        )
        await message.answer(ACTIVE_TICKET_UNAVAILABLE_TEXT)
        return

    logger.info(
        "Operator live reply stored operator_id=%s ticket=%s",
        message.from_user.id,
        reply_result.ticket.public_number,
    )

    delivery_error = await deliver_operator_reply_to_client(
        bot,
        chat_id=reply_result.client_chat_id,
        public_number=reply_result.ticket.public_number,
        body=message.text,
        reply_markup=build_client_ticket_markup(ticket_public_id=reply_result.ticket.public_id),
        logger=logger,
    )
    if delivery_error is None:
        return

    await message.answer(
        build_reply_delivery_failed_text(reply_result.ticket.public_number, delivery_error)
    )


async def _resolve_target_ticket(
    *,
    message: Message,
    helpdesk_service_factory: HelpdeskServiceFactory,
    operator_active_ticket_store: OperatorActiveTicketStore,
    explicit_ticket_public_id: UUID | None,
) -> TicketDetailsSummary | None:
    if explicit_ticket_public_id is not None:
        async with helpdesk_service_factory() as helpdesk_service:
            return await helpdesk_service.get_ticket_details(
                ticket_public_id=explicit_ticket_public_id,
                actor_telegram_user_id=message.from_user.id if message.from_user is not None else None,
            )

    if message.from_user is None:
        return None

    return await resolve_active_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        helpdesk_service_factory=helpdesk_service_factory,
        operator_telegram_user_id=message.from_user.id,
    )
