from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from application.services.helpdesk import HelpdeskServiceFactory
from application.use_cases.tickets import QueuedTicketSummary, TicketDetailsSummary
from bot.callbacks import OperatorActionCallback
from domain.enums.tickets import TicketEventType, TicketMessageSenderType, TicketStatus
from domain.tickets import InvalidTicketTransitionError
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorPresenceHelper,
    TicketLockManager,
)

router = Router(name="operator")


class OperatorTicketStates(StatesGroup):
    replying = State()
    reassigning = State()


@router.message(Command("cancel"))
async def handle_cancel(
    message: Message,
    state: FSMContext,
) -> None:
    if await state.get_state() is None:
        await message.answer("No operator action is active.")
        return

    await state.clear()
    await message.answer("Operator action cancelled.")


@router.message(Command("queue"))
async def handle_queue(
    message: Message,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await message.answer("Service is temporarily busy. Please retry in a moment.")
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        queued_tickets = await helpdesk_service.list_queued_tickets(limit=10)

    if not queued_tickets:
        await message.answer("Queue is empty.")
        return

    await message.answer("Queued tickets:")
    for ticket in queued_tickets:
        await message.answer(
            _format_queued_ticket(ticket),
            reply_markup=_build_ticket_actions_markup(
                ticket_public_id=ticket.public_id,
                status=ticket.status,
            ),
        )


@router.message(Command("take"))
async def handle_take_next(
    message: Message,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    if message.from_user is None:
        await message.answer("Operator identity is unavailable for this action.")
        return

    if not await global_rate_limiter.allow():
        await message.answer("Service is temporarily busy. Please retry in a moment.")
        return

    await operator_presence.touch(operator_id=message.from_user.id)

    queue_lock = ticket_lock_manager.for_ticket("queue-next")
    if not await queue_lock.acquire():
        await message.answer("Queue acquisition is busy. Please retry in a moment.")
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            ticket = await helpdesk_service.assign_next_ticket_to_operator(
                telegram_user_id=message.from_user.id,
                display_name=message.from_user.full_name,
                username=message.from_user.username,
            )
            ticket_details = None
            if ticket is not None:
                ticket_details = await helpdesk_service.get_ticket_details(
                    ticket_public_id=ticket.public_id
                )
    finally:
        await queue_lock.release()

    if ticket is None:
        await message.answer("No queued ticket is currently available.")
        return

    if ticket_details is None:
        await message.answer(
            f"Took next ticket {ticket.public_number}. "
            f"Current status={ticket.status.value}."
        )
        return

    await message.answer(
        _format_ticket_details(ticket_details),
        reply_markup=_build_ticket_actions_markup(
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
        await message.answer("Usage: /ticket <ticket_public_id>")
        return

    ticket_public_id = _parse_ticket_public_id(command.args.strip())
    if ticket_public_id is None:
        await message.answer("Invalid ticket identifier.")
        return

    if not await global_rate_limiter.allow():
        await message.answer("Service is temporarily busy. Please retry in a moment.")
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id
        )

    if ticket_details is None:
        await message.answer("Ticket not found.")
        return

    await message.answer(
        _format_ticket_details(ticket_details),
        reply_markup=_build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.message(Command("stats"))
async def handle_stats(
    message: Message,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await message.answer("Service is temporarily busy. Please retry in a moment.")
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        stats = await helpdesk_service.get_basic_stats()

    lines = [
        "Ticket stats:",
        f"total={stats.total}",
        f"open={stats.open_total}",
    ]
    for status, count in sorted(stats.by_status.items(), key=lambda item: item[0].value):
        lines.append(f"{status.value}={count}")

    await message.answer("\n".join(lines))


@router.callback_query(OperatorActionCallback.filter(F.action == "view"))
async def handle_view_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    ticket_public_id = _parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await _respond_to_operator(callback, "Invalid ticket identifier.")
        return

    if not await global_rate_limiter.allow():
        await _respond_to_operator(
            callback,
            "Service is temporarily busy. Please retry in a moment.",
        )
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id
        )

    if ticket_details is None:
        await _respond_to_operator(callback, "Ticket not found.")
        return

    await callback.answer(f"Viewing {ticket_details.public_number}")
    if callback.message is not None:
        await callback.message.answer(
            _format_ticket_details(ticket_details),
            reply_markup=_build_ticket_actions_markup(
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

    async with _operator_ticket_action(
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
                )
                if ticket is not None:
                    ticket_details = await helpdesk_service.get_ticket_details(
                        ticket_public_id=ticket.public_id
                    )
            except InvalidTicketTransitionError as exc:
                error_message = str(exc)

    if error_message is not None:
        await _respond_to_operator(callback, error_message)
        return

    if ticket is None:
        await _respond_to_operator(callback, "Ticket not found.")
        return

    if ticket.event_type == TicketEventType.REASSIGNED:
        answer_text = f"Ticket {ticket.public_number} reassigned."
    else:
        answer_text = f"Ticket {ticket.public_number} assigned."

    if callback.message is None or ticket_details is None:
        await _respond_to_operator(callback, answer_text)
        return

    await callback.answer(answer_text)
    await callback.message.answer(
        _format_ticket_details(ticket_details),
        reply_markup=_build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "reply"))
async def handle_reply_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    ticket_public_id = _parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await _respond_to_operator(callback, "Invalid ticket identifier.")
        return

    if not await global_rate_limiter.allow():
        await _respond_to_operator(
            callback,
            "Service is temporarily busy. Please retry in a moment.",
        )
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id
        )

    if ticket_details is None:
        await _respond_to_operator(callback, "Ticket not found.")
        return

    await state.set_state(OperatorTicketStates.replying)
    await state.update_data(ticket_public_id=str(ticket_public_id))
    await _respond_to_operator(
        callback,
        f"Reply mode enabled for {ticket_details.public_number}.",
        (
            f"Send the reply text for {ticket_details.public_number}.\n"
            "Use /cancel to abort."
        ),
    )


@router.message(StateFilter(OperatorTicketStates.replying), F.text)
async def handle_reply_message(
    message: Message,
    state: FSMContext,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    if message.from_user is None or message.text is None:
        await message.answer("Operator identity is unavailable for this action.")
        return

    if message.text.startswith("/"):
        await message.answer("Reply mode is active. Send text or use /cancel.")
        return

    if not await global_rate_limiter.allow():
        await message.answer("Service is temporarily busy. Please retry in a moment.")
        return

    await operator_presence.touch(operator_id=message.from_user.id)

    state_data = await state.get_data()
    ticket_public_id = _parse_ticket_public_id(state_data.get("ticket_public_id"))
    if ticket_public_id is None:
        await state.clear()
        await message.answer("Reply context is missing. Start the reply action again.")
        return

    lock = ticket_lock_manager.for_ticket(str(ticket_public_id))
    if not await lock.acquire():
        await message.answer("Ticket is being processed by another operator.")
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            try:
                reply_result = await helpdesk_service.reply_to_ticket_as_operator(
                    ticket_public_id=ticket_public_id,
                    telegram_user_id=message.from_user.id,
                    display_name=message.from_user.full_name,
                    username=message.from_user.username,
                    telegram_message_id=message.message_id,
                    text=message.text,
                )
            except InvalidTicketTransitionError as exc:
                await state.clear()
                await message.answer(str(exc))
                return

            if reply_result is None:
                await state.clear()
                await message.answer("Ticket not found.")
                return

            ticket_details = await helpdesk_service.get_ticket_details(
                ticket_public_id=ticket_public_id
            )
    finally:
        await lock.release()

    await state.clear()

    delivery_error: str | None = None
    try:
        await bot.send_message(
            reply_result.client_chat_id,
            f"Reply for ticket {reply_result.ticket.public_number}:\n{message.text}",
        )
    except TelegramAPIError as exc:
        delivery_error = str(exc)

    if delivery_error is None:
        await message.answer(f"Reply sent for {reply_result.ticket.public_number}.")
    else:
        await message.answer(
            f"Reply saved for {reply_result.ticket.public_number}, "
            f"but client delivery failed: {delivery_error}"
        )

    if ticket_details is not None:
        await message.answer(
            _format_ticket_details(ticket_details),
            reply_markup=_build_ticket_actions_markup(
                ticket_public_id=ticket_details.public_id,
                status=ticket_details.status,
            ),
        )


@router.callback_query(OperatorActionCallback.filter(F.action == "reassign"))
async def handle_reassign_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    ticket_public_id = _parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await _respond_to_operator(callback, "Invalid ticket identifier.")
        return

    if not await global_rate_limiter.allow():
        await _respond_to_operator(
            callback,
            "Service is temporarily busy. Please retry in a moment.",
        )
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id
        )

    if ticket_details is None:
        await _respond_to_operator(callback, "Ticket not found.")
        return

    await state.set_state(OperatorTicketStates.reassigning)
    await state.update_data(ticket_public_id=str(ticket_public_id))
    await _respond_to_operator(
        callback,
        f"Reassign mode enabled for {ticket_details.public_number}.",
        (
            "Send the target operator Telegram user ID, optionally followed by a display "
            "name.\nExample: 123456789 Jane Doe\nUse /cancel to abort."
        ),
    )


@router.message(StateFilter(OperatorTicketStates.reassigning), F.text)
async def handle_reassign_message(
    message: Message,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    if message.text is None:
        await message.answer("Send the target operator Telegram user ID.")
        return

    if message.text.startswith("/"):
        await message.answer("Reassign mode is active. Send operator data or use /cancel.")
        return

    if not await global_rate_limiter.allow():
        await message.answer("Service is temporarily busy. Please retry in a moment.")
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    target = _parse_reassign_target(message.text)
    if target is None:
        await message.answer(
            "Invalid input. Send a Telegram user ID, optionally followed by a display name."
        )
        return

    state_data = await state.get_data()
    ticket_public_id = _parse_ticket_public_id(state_data.get("ticket_public_id"))
    if ticket_public_id is None:
        await state.clear()
        await message.answer("Reassign context is missing. Start the action again.")
        return

    lock = ticket_lock_manager.for_ticket(str(ticket_public_id))
    if not await lock.acquire():
        await message.answer("Ticket is being processed by another operator.")
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            try:
                ticket = await helpdesk_service.assign_ticket_to_operator(
                    ticket_public_id=ticket_public_id,
                    telegram_user_id=target[0],
                    display_name=target[1],
                    username=None,
                )
            except InvalidTicketTransitionError as exc:
                await state.clear()
                await message.answer(str(exc))
                return

            if ticket is None:
                await state.clear()
                await message.answer("Ticket not found.")
                return

            ticket_details = await helpdesk_service.get_ticket_details(
                ticket_public_id=ticket_public_id
            )
    finally:
        await lock.release()

    await state.clear()

    if ticket_details is None:
        await message.answer(f"Ticket {ticket.public_number} updated.")
        return

    if ticket.event_type == TicketEventType.REASSIGNED:
        response_text = f"Ticket {ticket.public_number} reassigned."
    else:
        response_text = f"Ticket {ticket.public_number} assigned."

    await message.answer(response_text)
    await message.answer(
        _format_ticket_details(ticket_details),
        reply_markup=_build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "close"))
async def handle_close_action(
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

    async with _operator_ticket_action(
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
                ticket = await helpdesk_service.close_ticket(ticket_public_id=ticket_public_id)
                if ticket is not None:
                    ticket_details = await helpdesk_service.get_ticket_details(
                        ticket_public_id=ticket_public_id
                    )
            except InvalidTicketTransitionError as exc:
                error_message = str(exc)

    if error_message is not None:
        await _respond_to_operator(callback, error_message)
        return

    if ticket is None:
        await _respond_to_operator(callback, "Ticket not found.")
        return

    if callback.message is None or ticket_details is None:
        await _respond_to_operator(callback, f"Ticket {ticket.public_number} closed.")
        return

    await callback.answer(f"Ticket {ticket.public_number} closed.")
    await callback.message.answer(
        _format_ticket_details(ticket_details),
        reply_markup=_build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
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

    async with _operator_ticket_action(
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
                ticket = await helpdesk_service.escalate_ticket(ticket_public_id=ticket_public_id)
                if ticket is not None:
                    ticket_details = await helpdesk_service.get_ticket_details(
                        ticket_public_id=ticket_public_id
                    )
            except InvalidTicketTransitionError as exc:
                error_message = str(exc)

    if error_message is not None:
        await _respond_to_operator(callback, error_message)
        return

    if ticket is None:
        await _respond_to_operator(callback, "Ticket not found.")
        return

    if callback.message is None or ticket_details is None:
        await _respond_to_operator(callback, f"Ticket {ticket.public_number} escalated.")
        return

    await callback.answer(f"Ticket {ticket.public_number} escalated.")
    await callback.message.answer(
        _format_ticket_details(ticket_details),
        reply_markup=_build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@asynccontextmanager
async def _operator_ticket_action(
    *,
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> AsyncIterator[UUID | None]:
    ticket_public_id = _parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await _respond_to_operator(callback, "Invalid ticket identifier.")
        yield None
        return

    if not await global_rate_limiter.allow():
        await _respond_to_operator(
            callback,
            "Service is temporarily busy. Please retry in a moment.",
        )
        yield None
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    lock = ticket_lock_manager.for_ticket(callback_data.ticket_public_id)
    if not await lock.acquire():
        await _respond_to_operator(
            callback,
            "Ticket is being processed by another operator.",
        )
        yield None
        return

    try:
        yield ticket_public_id
    finally:
        await lock.release()


async def _respond_to_operator(
    callback: CallbackQuery,
    answer_text: str,
    message_text: str | None = None,
) -> None:
    await callback.answer(answer_text)
    if callback.message is not None and message_text is not None:
        await callback.message.answer(message_text)


def _build_ticket_actions_markup(
    *,
    ticket_public_id: UUID,
    status: TicketStatus,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)

    first_row = [
        (
            "View",
            OperatorActionCallback(action="view", ticket_public_id=callback_value).pack(),
        )
    ]
    if status == TicketStatus.QUEUED:
        first_row.append(
            (
                "Take",
                OperatorActionCallback(action="take", ticket_public_id=callback_value).pack(),
            )
        )
    elif status in {TicketStatus.ASSIGNED, TicketStatus.ESCALATED}:
        first_row.append(
            (
                "Reply",
                OperatorActionCallback(action="reply", ticket_public_id=callback_value).pack(),
            )
        )
    builder.row(*[_build_callback_button(text, data) for text, data in first_row])

    second_row: list[tuple[str, str]] = []
    if status in {TicketStatus.QUEUED, TicketStatus.ASSIGNED}:
        second_row.append(
            (
                "Escalate",
                OperatorActionCallback(action="escalate", ticket_public_id=callback_value).pack(),
            )
        )
    if status != TicketStatus.CLOSED:
        second_row.append(
            (
                "Close",
                OperatorActionCallback(action="close", ticket_public_id=callback_value).pack(),
            )
        )
    if second_row:
        builder.row(*[_build_callback_button(text, data) for text, data in second_row])

    if status != TicketStatus.CLOSED:
        builder.row(
            _build_callback_button(
                "Reassign",
                OperatorActionCallback(action="reassign", ticket_public_id=callback_value).pack(),
            )
        )

    return builder.as_markup()


def _build_callback_button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _format_queued_ticket(ticket: QueuedTicketSummary) -> str:
    return "\n".join(
        [
            f"{ticket.public_number}",
            f"Public ID: {ticket.public_id}",
            f"Status: {ticket.status.value}",
            f"Priority: {ticket.priority}",
            f"Subject: {ticket.subject}",
        ]
    )


def _format_ticket_details(ticket: TicketDetailsSummary) -> str:
    assigned_operator = "unassigned"
    if ticket.assigned_operator_id is not None:
        assigned_name = ticket.assigned_operator_name or "operator"
        assigned_operator = f"{assigned_name} (id={ticket.assigned_operator_id})"

    lines = [
        f"{ticket.public_number}",
        f"Public ID: {ticket.public_id}",
        f"Status: {ticket.status.value}",
        f"Priority: {ticket.priority}",
        f"Subject: {ticket.subject}",
        f"Assigned: {assigned_operator}",
        (
            "Last message: "
            f"{_format_last_message(ticket.last_message_text, ticket.last_message_sender_type)}"
        ),
    ]
    return "\n".join(lines)


def _format_last_message(
    message_text: str | None,
    sender_type: TicketMessageSenderType | None,
) -> str:
    if not message_text:
        return "-"

    preview = " ".join(message_text.split())
    if len(preview) > 120:
        preview = f"{preview[:117]}..."

    if sender_type is None:
        return preview

    return f"[{sender_type.value}] {preview}"


def _parse_ticket_public_id(value: str | None) -> UUID | None:
    if value is None:
        return None

    try:
        return UUID(value)
    except ValueError:
        return None


def _parse_reassign_target(text: str) -> tuple[int, str] | None:
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return None

    try:
        telegram_user_id = int(parts[0])
    except ValueError:
        return None

    display_name = parts[1].strip() if len(parts) > 1 else f"Operator {telegram_user_id}"
    if not display_name:
        display_name = f"Operator {telegram_user_id}"
    return telegram_user_id, display_name
