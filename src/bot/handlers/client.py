from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from application.services.helpdesk import HelpdeskServiceFactory
from infrastructure.redis.contracts import ChatRateLimiter, GlobalRateLimiter, TicketStreamPublisher

router = Router(name="client")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_client_text(
    message: Message,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    chat_rate_limiter: ChatRateLimiter,
    ticket_stream_publisher: TicketStreamPublisher,
) -> None:
    if message.text is None:
        return

    if not await global_rate_limiter.allow():
        await message.answer("Service is temporarily busy. Please retry in a moment.")
        return

    if not await chat_rate_limiter.allow(chat_id=message.chat.id):
        await message.answer("Too many requests from this chat. Please slow down.")
        return

    async with helpdesk_service_factory() as helpdesk_service:
        ticket = await helpdesk_service.create_ticket_from_client_message(
            client_chat_id=message.chat.id,
            telegram_message_id=message.message_id,
            text=message.text,
        )

    await ticket_stream_publisher.publish_new_ticket(
        ticket_id=str(ticket.public_id),
        client_chat_id=message.chat.id,
        subject=message.text.strip()[:255] or "Client request",
    )

    await message.answer(
        f"Ticket {ticket.public_number} created. "
        "An operator will respond in a later iteration."
    )
