from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from bot.delivery import deliver_client_message_to_operator
from bot.texts.client import build_ticket_created_text, build_ticket_message_added_text
from bot.texts.common import CHAT_RATE_LIMIT_TEXT, SERVICE_UNAVAILABLE_TEXT
from domain.tickets import InvalidTicketTransitionError
from infrastructure.redis.contracts import (
    ChatRateLimiter,
    GlobalRateLimiter,
    TicketStreamPublisher,
)

router = Router(name="client")
logger = logging.getLogger(__name__)


@router.message(F.text & ~F.text.startswith("/"))
async def handle_client_text(
    message: Message,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    chat_rate_limiter: ChatRateLimiter,
    ticket_stream_publisher: TicketStreamPublisher,
) -> None:
    if message.text is None:
        return

    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    if not await chat_rate_limiter.allow(chat_id=message.chat.id):
        await message.answer(CHAT_RATE_LIMIT_TEXT)
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            ticket = await helpdesk_service.create_ticket_from_client_message(
                client_chat_id=message.chat.id,
                telegram_message_id=message.message_id,
                text=message.text,
            )
            ticket_details = None
            if not ticket.created:
                ticket_details = await helpdesk_service.get_ticket_details(
                    ticket_public_id=ticket.public_id,
                )
    except InvalidTicketTransitionError as exc:
        await message.answer(str(exc))
        return

    logger.info(
        "Client ticket message processed client_chat_id=%s ticket=%s created=%s",
        message.chat.id,
        ticket.public_number,
        ticket.created,
    )

    if ticket.created:
        await ticket_stream_publisher.publish_new_ticket(
            ticket_id=str(ticket.public_id),
            client_chat_id=message.chat.id,
            subject=message.text.strip()[:255] or "Обращение клиента",
        )
        await message.answer(build_ticket_created_text(ticket.public_number))
        return

    if (
        ticket_details is not None
        and ticket_details.assigned_operator_telegram_user_id is not None
    ):
        delivery_error = await deliver_client_message_to_operator(
            bot,
            chat_id=ticket_details.assigned_operator_telegram_user_id,
            public_number=ticket.public_number,
            body=message.text,
            logger=logger,
        )
        if delivery_error is not None:
            logger.warning(
                "Failed to forward client message to operator "
                "ticket=%s operator_chat_id=%s error=%s",
                ticket.public_number,
                ticket_details.assigned_operator_telegram_user_id,
                delivery_error,
            )

    await message.answer(build_ticket_message_added_text(ticket.public_number))
