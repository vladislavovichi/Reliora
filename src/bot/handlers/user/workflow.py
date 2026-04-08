from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from bot.delivery import deliver_client_message_to_operator
from bot.keyboards.inline.client_actions import build_client_ticket_markup
from bot.keyboards.inline.operator_actions import (
    build_ticket_actions_markup,
    build_ticket_switch_markup,
)
from bot.texts.client import build_ticket_created_text, build_ticket_message_added_text
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from domain.tickets import InvalidTicketTransitionError
from infrastructure.redis.contracts import (
    OperatorActiveTicketStore,
    TicketLiveSessionStore,
    TicketStreamPublisher,
)


async def process_client_ticket_message(
    *,
    message: Message,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_stream_publisher: TicketStreamPublisher,
    logger: logging.Logger,
    category_id: int | None = None,
) -> None:
    if message.text is None:
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            ticket = (
                await helpdesk_service.create_ticket_from_client_message(
                    client_chat_id=message.chat.id,
                    telegram_message_id=message.message_id,
                    text=message.text,
                )
                if category_id is None
                else await helpdesk_service.create_ticket_from_client_intake(
                    client_chat_id=message.chat.id,
                    telegram_message_id=message.message_id,
                    category_id=category_id,
                    text=message.text,
                )
            )
            ticket_details = await helpdesk_service.get_ticket_details(
                ticket_public_id=ticket.public_id,
            )
    except InvalidTicketTransitionError as exc:
        await message.answer(str(exc))
        return

    if ticket_details is None:
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await ticket_live_session_store.refresh_session(
        ticket_public_id=str(ticket.public_id),
        client_chat_id=message.chat.id,
        operator_telegram_user_id=ticket_details.assigned_operator_telegram_user_id,
    )

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
            subject=ticket_details.subject,
        )
        await message.answer(
            build_ticket_created_text(ticket.public_number),
            reply_markup=build_client_ticket_markup(ticket_public_id=ticket.public_id),
        )
        return

    operator_chat_id = ticket_details.assigned_operator_telegram_user_id
    operator_connected = operator_chat_id is not None
    if operator_chat_id is not None:
        active_ticket_public_id = await operator_active_ticket_store.get_active_ticket(
            operator_id=operator_chat_id
        )
        is_active_context = active_ticket_public_id == str(ticket.public_id)
        delivery_error = await deliver_client_message_to_operator(
            bot,
            chat_id=operator_chat_id,
            public_number=ticket.public_number,
            body=message.text,
            reply_markup=(
                build_ticket_actions_markup(
                    ticket_public_id=ticket.public_id,
                    status=ticket_details.status,
                )
                if is_active_context
                else build_ticket_switch_markup(ticket_public_id=ticket.public_id)
            ),
            active_context=is_active_context,
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

    await message.answer(
        build_ticket_message_added_text(
            ticket.public_number,
            operator_connected=operator_connected,
        ),
        reply_markup=build_client_ticket_markup(ticket_public_id=ticket.public_id),
    )
