from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from application.services.helpdesk import HelpdeskServiceFactory
from bot.formatters.operator import (
    format_macro_list,
    format_queued_ticket,
    format_status,
    format_tags,
    format_ticket_details,
    format_ticket_tags_response,
)
from bot.handlers.operator.parsers import parse_ticket_argument_with_text, parse_ticket_public_id
from bot.keyboards.inline.operator_actions import (
    build_macro_actions_markup,
    build_ticket_actions_markup,
)
from bot.texts.buttons import CANCEL_BUTTON_TEXT, QUEUE_BUTTON_TEXT, TAKE_NEXT_BUTTON_TEXT
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_LOCKED_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.operator import (
    MACROS_EMPTY_TEXT,
    NO_QUEUE_TICKETS_TEXT,
    OPERATOR_ACTION_CANCELLED_TEXT,
    OPERATOR_ACTION_IDLE_TEXT,
    OPERATOR_UNKNOWN_TEXT,
    QUEUE_BUSY_TEXT,
    QUEUE_EMPTY_TEXT,
    QUEUE_HEADER_TEXT,
    TAGS_EMPTY_TEXT,
    build_available_tags_text,
    build_tag_added_text,
    build_tag_already_added_text,
    build_tag_missing_text,
    build_tag_removed_text,
    invalid_add_tag_usage_text,
    invalid_macros_usage_text,
    invalid_remove_tag_usage_text,
    invalid_tags_usage_text,
    invalid_ticket_usage_text,
)
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorPresenceHelper,
    TicketLockManager,
)

router = Router(name="operator_commands")


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
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        queued_tickets = await helpdesk_service.list_queued_tickets(
            limit=10,
            actor_telegram_user_id=message.from_user.id if message.from_user is not None else None,
        )

    if not queued_tickets:
        await message.answer(QUEUE_EMPTY_TEXT)
        return

    await message.answer(QUEUE_HEADER_TEXT)
    for ticket in queued_tickets:
        await message.answer(
            format_queued_ticket(ticket),
            reply_markup=build_ticket_actions_markup(
                ticket_public_id=ticket.public_id,
                status=ticket.status,
            ),
        )


@router.message(Command("take"))
@router.message(F.text == TAKE_NEXT_BUTTON_TEXT)
async def handle_take_next(
    message: Message,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    if message.from_user is None:
        await message.answer(OPERATOR_UNKNOWN_TEXT)
        return

    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=message.from_user.id)

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
        from bot.texts.operator import build_take_next_fallback_text

        await message.answer(
            build_take_next_fallback_text(ticket.public_number, format_status(ticket.status))
        )
        return

    await message.answer(
        format_ticket_details(ticket_details),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.message(Command("ticket"))
async def handle_ticket_details(
    message: Message,
    command: CommandObject,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if command.args is None:
        await message.answer(invalid_ticket_usage_text())
        return

    ticket_public_id = parse_ticket_public_id(command.args.strip())
    if ticket_public_id is None:
        await message.answer(INVALID_TICKET_ID_TEXT)
        return

    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor_telegram_user_id=message.from_user.id if message.from_user is not None else None,
        )

    if ticket_details is None:
        await message.answer(TICKET_NOT_FOUND_TEXT)
        return

    await message.answer(
        format_ticket_details(ticket_details),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.message(Command("macros"))
async def handle_macros(
    message: Message,
    command: CommandObject,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    ticket_public_id = None
    if command.args is not None and command.args.strip():
        ticket_public_id = parse_ticket_public_id(command.args.strip())
        if ticket_public_id is None:
            await message.answer(invalid_macros_usage_text())
            return

    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    actor_telegram_user_id = message.from_user.id if message.from_user is not None else None
    async with helpdesk_service_factory() as helpdesk_service:
        macros = await helpdesk_service.list_macros(
            actor_telegram_user_id=actor_telegram_user_id
        )
        ticket_details = None
        if ticket_public_id is not None:
            ticket_details = await helpdesk_service.get_ticket_details(
                ticket_public_id=ticket_public_id,
                actor_telegram_user_id=actor_telegram_user_id,
            )

    if ticket_public_id is not None and ticket_details is None:
        await message.answer(TICKET_NOT_FOUND_TEXT)
        return

    if not macros:
        await message.answer(MACROS_EMPTY_TEXT)
        return

    await message.answer(
        format_macro_list(macros, ticket_details),
        reply_markup=(
            build_macro_actions_markup(ticket_public_id=ticket_public_id, macros=macros)
            if ticket_public_id is not None
            else None
        ),
    )


@router.message(Command("tags"))
async def handle_ticket_tags(
    message: Message,
    command: CommandObject,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if command.args is None:
        await message.answer(invalid_tags_usage_text())
        return

    ticket_public_id = parse_ticket_public_id(command.args.strip())
    if ticket_public_id is None:
        await message.answer(INVALID_TICKET_ID_TEXT)
        return

    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        actor_telegram_user_id = message.from_user.id if message.from_user is not None else None
        tags_result = await helpdesk_service.list_ticket_tags(
            ticket_public_id=ticket_public_id,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        available_tags = await helpdesk_service.list_available_tags(
            actor_telegram_user_id=actor_telegram_user_id
        )

    if tags_result is None:
        await message.answer(TICKET_NOT_FOUND_TEXT)
        return

    await message.answer(
        format_ticket_tags_response(
            tags_result.public_number,
            tags_result.tags,
            available_tags,
        )
    )


@router.message(Command("alltags"))
async def handle_all_tags(
    message: Message,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        available_tags = await helpdesk_service.list_available_tags(
            actor_telegram_user_id=message.from_user.id if message.from_user is not None else None
        )

    if not available_tags:
        await message.answer(TAGS_EMPTY_TEXT)
        return

    await message.answer(build_available_tags_text(tuple(available_tags)))


@router.message(Command("addtag"))
async def handle_add_tag(
    message: Message,
    command: CommandObject,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    parsed = parse_ticket_argument_with_text(command.args)
    if parsed is None:
        await message.answer(invalid_add_tag_usage_text())
        return

    ticket_public_id, tag_name = parsed
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    actor_telegram_user_id = message.from_user.id if message.from_user is not None else None
    lock = ticket_lock_manager.for_ticket(str(ticket_public_id))
    if not await lock.acquire():
        await message.answer(TICKET_LOCKED_TEXT)
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            result = await helpdesk_service.add_tag_to_ticket(
                ticket_public_id=ticket_public_id,
                tag_name=tag_name,
                actor_telegram_user_id=actor_telegram_user_id,
            )
    finally:
        await lock.release()

    if result is None:
        await message.answer(TICKET_NOT_FOUND_TEXT)
        return

    tag_list = format_tags(result.tags)
    if result.changed:
        await message.answer(
            build_tag_added_text(
                result.ticket.public_number,
                result.tag,
                tag_list,
            )
        )
        return

    await message.answer(
        build_tag_already_added_text(
            result.ticket.public_number,
            result.tag,
            tag_list,
        )
    )


@router.message(Command("rmtag"))
async def handle_remove_tag(
    message: Message,
    command: CommandObject,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    parsed = parse_ticket_argument_with_text(command.args)
    if parsed is None:
        await message.answer(invalid_remove_tag_usage_text())
        return

    ticket_public_id, tag_name = parsed
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    actor_telegram_user_id = message.from_user.id if message.from_user is not None else None
    lock = ticket_lock_manager.for_ticket(str(ticket_public_id))
    if not await lock.acquire():
        await message.answer(TICKET_LOCKED_TEXT)
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            result = await helpdesk_service.remove_tag_from_ticket(
                ticket_public_id=ticket_public_id,
                tag_name=tag_name,
                actor_telegram_user_id=actor_telegram_user_id,
            )
    finally:
        await lock.release()

    if result is None:
        await message.answer(TICKET_NOT_FOUND_TEXT)
        return

    tag_list = format_tags(result.tags)
    if result.changed:
        await message.answer(
            build_tag_removed_text(
                result.ticket.public_number,
                result.tag,
                tag_list,
            )
        )
        return

    await message.answer(build_tag_missing_text(result.ticket.public_number, result.tag, tag_list))
