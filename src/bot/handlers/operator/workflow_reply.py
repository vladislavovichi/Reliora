from __future__ import annotations

import logging
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.filters import MagicData, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.use_cases.tickets.summaries import (
    TicketDetailsSummary,
    build_ticket_attachment_summary,
)
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import (
    build_operator_identity,
    build_operator_reply_command,
    build_request_actor,
)
from bot.callbacks import OperatorActionCallback
from bot.delivery import deliver_operator_reply_to_client
from bot.handlers.common.ticket_attachments import AttachmentRejectedError, extract_ticket_content
from bot.handlers.operator.active_context import (
    activate_ticket_for_operator,
    clear_active_ticket_for_operator,
    resolve_active_ticket_for_operator,
)
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.handlers.operator.ticket_surfaces import send_ticket_details
from bot.keyboards.inline.client_actions import build_client_ticket_markup
from bot.keyboards.inline.operator_actions import build_ticket_actions_markup
from bot.texts.common import (
    ATTACHMENT_NOT_SUPPORTED_TEXT,
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
    build_reply_sent_text,
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
SUPPORTED_TICKET_MEDIA_FILTER = F.photo | F.document | F.voice | F.video


@router.callback_query(OperatorActionCallback.filter(F.action == "reply"))
async def handle_reply_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    state: FSMContext,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
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

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        ticket_details = await helpdesk_backend.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor=build_request_actor(callback.from_user),
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
    if not isinstance(callback.message, Message):
        return

    await send_ticket_details(
        message=callback.message,
        ticket_details=ticket_details,
        is_active_context=True,
    )


@router.message(
    MagicData(F.event_user_role.in_({UserRole.OPERATOR, UserRole.SUPER_ADMIN})),
    StateFilter(None),
    F.text & ~F.text.startswith("/"),
)
@router.message(
    MagicData(F.event_user_role.in_({UserRole.OPERATOR, UserRole.SUPER_ADMIN})),
    StateFilter(None),
    SUPPORTED_TICKET_MEDIA_FILTER,
)
async def handle_operator_message(
    message: Message,
    bot: Bot,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_lock_manager: TicketLockManager,
) -> None:
    await _handle_operator_message(
        message=message,
        bot=bot,
        helpdesk_backend_client_factory=helpdesk_backend_client_factory,
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
        operator_active_ticket_store=operator_active_ticket_store,
        ticket_live_session_store=ticket_live_session_store,
        ticket_lock_manager=ticket_lock_manager,
    )


@router.message(
    MagicData(F.event_user_role.in_({UserRole.OPERATOR, UserRole.SUPER_ADMIN})),
    StateFilter(None),
    F.content_type.in_({"animation", "audio", "sticker", "video_note"}),
)
async def handle_operator_unsupported_attachment(message: Message) -> None:
    await message.answer(ATTACHMENT_NOT_SUPPORTED_TEXT)


async def _handle_operator_message(
    *,
    message: Message,
    bot: Bot,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_lock_manager: TicketLockManager,
    explicit_ticket_public_id: UUID | None = None,
) -> None:
    try:
        content = await extract_ticket_content(message, bot=bot)
    except AttachmentRejectedError as exc:
        await message.answer(str(exc))
        return
    if message.from_user is None or content is None:
        await message.answer(OPERATOR_UNKNOWN_TEXT)
        return
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=message.from_user.id)

    ticket_details = await _resolve_target_ticket(
        message=message,
        helpdesk_backend_client_factory=helpdesk_backend_client_factory,
        operator_active_ticket_store=operator_active_ticket_store,
        explicit_ticket_public_id=explicit_ticket_public_id,
    )
    if ticket_details is None:
        await message.answer(
            REPLY_CONTEXT_LOST_TEXT
            if explicit_ticket_public_id is not None
            else ACTIVE_TICKET_REQUIRED_TEXT
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
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            try:
                operator = build_operator_identity(message.from_user)
                if operator is None:
                    await message.answer(OPERATOR_UNKNOWN_TEXT)
                    return
                reply_result = await helpdesk_backend.reply_to_ticket_as_operator(
                    build_operator_reply_command(
                        ticket_public_id=ticket_details.public_id,
                        operator=operator,
                        message=message,
                        content=content,
                    ),
                    actor=build_request_actor(message.from_user),
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
        text=content.text,
        attachment=(
            build_ticket_attachment_summary(content.attachment)
            if content.attachment is not None
            else None
        ),
        reply_markup=build_client_ticket_markup(ticket_public_id=reply_result.ticket.public_id),
        logger=logger,
    )
    if delivery_error is None:
        await message.answer(
            build_reply_sent_text(reply_result.ticket.public_number),
            reply_markup=build_ticket_actions_markup(
                ticket_public_id=reply_result.ticket.public_id,
                status=reply_result.ticket.status,
            ),
        )
        return

    await message.answer(
        build_reply_delivery_failed_text(reply_result.ticket.public_number, delivery_error),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=reply_result.ticket.public_id,
            status=reply_result.ticket.status,
        ),
    )


async def _resolve_target_ticket(
    *,
    message: Message,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    operator_active_ticket_store: OperatorActiveTicketStore,
    explicit_ticket_public_id: UUID | None,
) -> TicketDetailsSummary | None:
    if explicit_ticket_public_id is not None:
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            return await helpdesk_backend.get_ticket_details(
                ticket_public_id=explicit_ticket_public_id,
                actor=build_request_actor(message.from_user),
            )

    if message.from_user is None:
        return None

    return await resolve_active_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        helpdesk_backend_client_factory=helpdesk_backend_client_factory,
        operator_telegram_user_id=message.from_user.id,
    )
