from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from uuid import UUID

from application.services.helpdesk import HelpdeskServiceFactory
from bot.callbacks import OperatorActionCallback
from infrastructure.redis.contracts import GlobalRateLimiter, OperatorPresenceHelper, TicketLockManager

router = Router(name="operator")


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


@router.callback_query(OperatorActionCallback.filter(F.action == "take"))
async def handle_take_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    ticket_public_id = _parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await callback.answer("Invalid ticket identifier.")
        return

    if not await global_rate_limiter.allow():
        await callback.answer("Service is temporarily busy. Please retry in a moment.")
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    lock = ticket_lock_manager.for_ticket(callback_data.ticket_public_id)
    if not await lock.acquire():
        await callback.answer("Ticket is being processed by another operator.")
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            ticket = await helpdesk_service.assign_ticket_to_operator(
                ticket_public_id=ticket_public_id,
                telegram_user_id=callback.from_user.id,
                display_name=callback.from_user.full_name,
                username=callback.from_user.username,
            )
    finally:
        await lock.release()

    if ticket is None:
        await callback.answer("Ticket not found.")
        return

    await callback.answer(f"Ticket {ticket.public_number} assigned.")
    if callback.message is not None:
        await callback.message.answer(
            f"Ticket {ticket.public_number} is now assigned to {callback.from_user.full_name}."
        )


@router.callback_query(OperatorActionCallback.filter(F.action == "reply"))
async def handle_reply_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    ticket_public_id = _parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await callback.answer("Invalid ticket identifier.")
        return

    if not await global_rate_limiter.allow():
        await callback.answer("Service is temporarily busy. Please retry in a moment.")
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    lock = ticket_lock_manager.for_ticket(callback_data.ticket_public_id)
    if not await lock.acquire():
        await callback.answer("Ticket is being processed by another operator.")
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            response_text = await helpdesk_service.acknowledge_reply_action(
                ticket_public_id=ticket_public_id,
            )
    finally:
        await lock.release()

    await callback.answer(response_text)
    if callback.message is not None:
        await callback.message.answer(response_text)


@router.callback_query(OperatorActionCallback.filter(F.action == "close"))
async def handle_close_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    ticket_public_id = _parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await callback.answer("Invalid ticket identifier.")
        return

    if not await global_rate_limiter.allow():
        await callback.answer("Service is temporarily busy. Please retry in a moment.")
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    lock = ticket_lock_manager.for_ticket(callback_data.ticket_public_id)
    if not await lock.acquire():
        await callback.answer("Ticket is being processed by another operator.")
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            ticket = await helpdesk_service.close_ticket(ticket_public_id=ticket_public_id)
    finally:
        await lock.release()

    if ticket is None:
        await callback.answer("Ticket not found.")
        return

    await callback.answer(f"Ticket {ticket.public_number} closed.")
    if callback.message is not None:
        await callback.message.answer(
            f"Ticket {ticket.public_number} closed successfully."
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
    ticket_public_id = _parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await callback.answer("Invalid ticket identifier.")
        return

    if not await global_rate_limiter.allow():
        await callback.answer("Service is temporarily busy. Please retry in a moment.")
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    lock = ticket_lock_manager.for_ticket(callback_data.ticket_public_id)
    if not await lock.acquire():
        await callback.answer("Ticket is being processed by another operator.")
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            response_text = await helpdesk_service.acknowledge_escalate_action(
                ticket_public_id=ticket_public_id,
            )
    finally:
        await lock.release()

    await callback.answer(response_text)
    if callback.message is not None:
        await callback.message.answer(response_text)


def _parse_ticket_public_id(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None
