from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk import HelpdeskServiceFactory
from bot.callbacks import OperatorActionCallback
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorPresenceHelper,
    TicketLockManager,
)

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
            ticket = await helpdesk_service.assign_ticket_to_operator(
                ticket_public_id=ticket_public_id,
                telegram_user_id=callback.from_user.id,
                display_name=callback.from_user.full_name,
                username=callback.from_user.username,
            )

    if ticket is None:
        await _respond_to_operator(callback, "Ticket not found.")
        return

    await _respond_to_operator(
        callback,
        f"Ticket {ticket.public_number} assigned.",
        f"Ticket {ticket.public_number} is now assigned to {callback.from_user.full_name}.",
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
            response_text = await helpdesk_service.acknowledge_reply_action(
                ticket_public_id=ticket_public_id,
            )

    await _respond_to_operator(callback, response_text, response_text)


@router.callback_query(OperatorActionCallback.filter(F.action == "close"))
async def handle_close_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
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
            ticket = await helpdesk_service.close_ticket(ticket_public_id=ticket_public_id)

    if ticket is None:
        await _respond_to_operator(callback, "Ticket not found.")
        return

    await _respond_to_operator(
        callback,
        f"Ticket {ticket.public_number} closed.",
        f"Ticket {ticket.public_number} closed successfully.",
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
            response_text = await helpdesk_service.acknowledge_escalate_action(
                ticket_public_id=ticket_public_id,
            )

    await _respond_to_operator(callback, response_text, response_text)


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


def _parse_ticket_public_id(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None
