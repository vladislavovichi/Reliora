from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import Message

from application.contracts.tickets import ClientTicketMessageCommand
from application.use_cases.tickets.summaries import build_ticket_attachment_summary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import build_client_ticket_message_command
from bot.delivery import deliver_client_message_to_operator
from bot.handlers.common.ticket_attachments import (
    AttachmentRejectedError,
    IncomingTicketContent,
    extract_ticket_content,
)
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
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_stream_publisher: TicketStreamPublisher,
    logger: logging.Logger,
    category_id: int | None = None,
    content: IncomingTicketContent | None = None,
) -> None:
    effective_content = content
    if effective_content is None:
        try:
            effective_content = await extract_ticket_content(message, bot=bot)
        except AttachmentRejectedError as exc:
            await message.answer(str(exc))
            return
    if effective_content is None:
        return

    command = build_client_ticket_message_command(
        message=message,
        content=effective_content,
        category_id=category_id,
    )
    await process_client_ticket_command(
        response_message=message,
        bot=bot,
        helpdesk_backend_client_factory=helpdesk_backend_client_factory,
        operator_active_ticket_store=operator_active_ticket_store,
        ticket_live_session_store=ticket_live_session_store,
        ticket_stream_publisher=ticket_stream_publisher,
        logger=logger,
        command=command,
        content=effective_content,
        category_id=category_id,
    )


async def process_client_ticket_command(
    *,
    response_message: Message,
    bot: Bot,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_stream_publisher: TicketStreamPublisher,
    logger: logging.Logger,
    command: ClientTicketMessageCommand,
    content: IncomingTicketContent,
    category_id: int | None = None,
) -> None:
    text = content.text
    attachment = content.attachment

    try:
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            ticket = (
                await helpdesk_backend.create_ticket_from_client_message(command)
                if category_id is None
                else await helpdesk_backend.create_ticket_from_client_intake(command)
            )
            ticket_details = await helpdesk_backend.get_ticket_details(
                ticket_public_id=ticket.public_id,
            )
    except InvalidTicketTransitionError as exc:
        await response_message.answer(str(exc))
        return

    if ticket_details is None:
        await response_message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await ticket_live_session_store.refresh_session(
        ticket_public_id=str(ticket.public_id),
        client_chat_id=command.client_chat_id,
        operator_telegram_user_id=ticket_details.assigned_operator_telegram_user_id,
    )

    logger.info(
        "Client ticket message processed client_chat_id=%s ticket=%s created=%s",
        command.client_chat_id,
        ticket.public_number,
        ticket.created,
    )

    if ticket.created:
        await ticket_stream_publisher.publish_new_ticket(
            ticket_id=str(ticket.public_id),
            client_chat_id=command.client_chat_id,
            subject=ticket_details.subject,
        )
        await response_message.answer(
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
            text=text,
            attachment=(
                build_ticket_attachment_summary(attachment) if attachment is not None else None
            ),
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

    await response_message.answer(
        build_ticket_message_added_text(
            ticket.public_number,
            operator_connected=operator_connected,
        ),
        reply_markup=build_client_ticket_markup(ticket_public_id=ticket.public_id),
    )


async def process_client_intake_submission(
    *,
    response_message: Message,
    bot: Bot,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_stream_publisher: TicketStreamPublisher,
    logger: logging.Logger,
    initial_command: ClientTicketMessageCommand,
    follow_up_command: ClientTicketMessageCommand | None = None,
) -> None:
    del bot, operator_active_ticket_store

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        ticket = await helpdesk_backend.create_ticket_from_client_intake(initial_command)
        if follow_up_command is not None:
            await helpdesk_backend.create_ticket_from_client_message(follow_up_command)
        ticket_details = await helpdesk_backend.get_ticket_details(
            ticket_public_id=ticket.public_id,
        )

    if ticket_details is None:
        await response_message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await ticket_live_session_store.refresh_session(
        ticket_public_id=str(ticket.public_id),
        client_chat_id=initial_command.client_chat_id,
        operator_telegram_user_id=ticket_details.assigned_operator_telegram_user_id,
    )

    logger.info(
        (
            "Client intake submission processed "
            "client_chat_id=%s ticket=%s created=%s has_follow_up=%s"
        ),
        initial_command.client_chat_id,
        ticket.public_number,
        ticket.created,
        follow_up_command is not None,
    )

    if ticket.created:
        await ticket_stream_publisher.publish_new_ticket(
            ticket_id=str(ticket.public_id),
            client_chat_id=initial_command.client_chat_id,
            subject=ticket_details.subject,
        )
        await response_message.answer(
            build_ticket_created_text(ticket.public_number),
            reply_markup=build_client_ticket_markup(ticket_public_id=ticket.public_id),
        )
        return

    await response_message.answer(
        build_ticket_message_added_text(
            ticket.public_number,
            operator_connected=ticket_details.assigned_operator_telegram_user_id is not None,
        ),
        reply_markup=build_client_ticket_markup(ticket_public_id=ticket.public_id),
    )
