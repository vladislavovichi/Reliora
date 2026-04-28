from __future__ import annotations

from aiogram import Bot
from aiogram.types import Message

from application.contracts.tickets import ClientTicketMessageCommand
from application.use_cases.tickets.summaries import build_ticket_attachment_summary
from bot.adapters.helpdesk import build_client_ticket_message_command
from bot.delivery import deliver_client_message_to_operator
from bot.handlers.common.ticket_attachments import (
    AttachmentRejectedError,
    IncomingTicketContent,
    extract_ticket_content,
)
from bot.handlers.user.intake_context import TicketRuntimeContext
from bot.keyboards.inline.client_actions import build_client_ticket_markup
from bot.keyboards.inline.operator_actions import (
    build_ticket_actions_markup,
    build_ticket_switch_markup,
)
from bot.texts.client import (
    build_ticket_created_text,
    build_ticket_created_with_missing_follow_up_text,
    build_ticket_message_added_text,
    build_ticket_message_added_with_missing_follow_up_text,
    build_ticket_message_recorded_text,
)
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from domain.enums.tickets import TicketEventType
from domain.tickets import InvalidTicketTransitionError


async def process_client_ticket_message(
    *,
    message: Message,
    bot: Bot,
    context: TicketRuntimeContext,
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
        context=context,
        command=command,
        content=effective_content,
        category_id=category_id,
    )


async def process_client_ticket_command(
    *,
    response_message: Message,
    bot: Bot,
    context: TicketRuntimeContext,
    command: ClientTicketMessageCommand,
    content: IncomingTicketContent,
    category_id: int | None = None,
) -> None:
    text = content.text
    attachment = content.attachment

    try:
        async with context.helpdesk_backend_client_factory() as helpdesk_backend:
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

    await context.ticket_live_session_store.refresh_session(
        ticket_public_id=str(ticket.public_id),
        client_chat_id=command.client_chat_id,
        operator_telegram_user_id=ticket_details.assigned_operator_telegram_user_id,
    )

    context.logger.info(
        "Client ticket message processed client_chat_id=%s ticket=%s created=%s",
        command.client_chat_id,
        ticket.public_number,
        ticket.created,
    )

    if ticket.created:
        await _publish_new_ticket_event(
            context=context,
            ticket_id=str(ticket.public_id),
            client_chat_id=command.client_chat_id,
            subject=ticket_details.subject,
            public_number=ticket.public_number,
        )
        await response_message.answer(
            build_ticket_created_text(ticket.public_number),
            reply_markup=build_client_ticket_markup(ticket_public_id=ticket.public_id),
        )
        return

    operator_chat_id = ticket_details.assigned_operator_telegram_user_id
    operator_connected = operator_chat_id is not None
    if (
        operator_chat_id is not None
        and ticket.event_type != TicketEventType.CLIENT_MESSAGE_DUPLICATE_COLLAPSED
    ):
        active_ticket_public_id = await context.operator_active_ticket_store.get_active_ticket(
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
            logger=context.logger,
        )
        if delivery_error is not None:
            context.logger.warning(
                "Failed to forward client message to operator "
                "ticket=%s operator_chat_id=%s error=%s",
                ticket.public_number,
                ticket_details.assigned_operator_telegram_user_id,
                delivery_error,
            )

    await response_message.answer(
        (
            build_ticket_message_recorded_text(ticket.public_number)
            if ticket.event_type == TicketEventType.CLIENT_MESSAGE_DUPLICATE_COLLAPSED
            else build_ticket_message_added_text(
                ticket.public_number,
                operator_connected=operator_connected,
            )
        ),
        reply_markup=build_client_ticket_markup(ticket_public_id=ticket.public_id),
    )


async def process_client_intake_submission(
    *,
    response_message: Message,
    bot: Bot,
    context: TicketRuntimeContext,
    initial_command: ClientTicketMessageCommand,
    follow_up_command: ClientTicketMessageCommand | None = None,
) -> None:
    del bot

    follow_up_recorded = follow_up_command is None
    try:
        async with context.helpdesk_backend_client_factory() as helpdesk_backend:
            ticket = await helpdesk_backend.create_ticket_from_client_intake(initial_command)
            if follow_up_command is not None:
                try:
                    await helpdesk_backend.create_ticket_from_client_message(follow_up_command)
                    follow_up_recorded = True
                except InvalidTicketTransitionError as exc:
                    context.logger.warning(
                        "Client intake follow-up rejected ticket=%s client_chat_id=%s error=%s",
                        ticket.public_number,
                        initial_command.client_chat_id,
                        exc,
                    )
                except RuntimeError as exc:
                    context.logger.warning(
                        "Client intake follow-up failed ticket=%s client_chat_id=%s error=%s",
                        ticket.public_number,
                        initial_command.client_chat_id,
                        exc,
                    )
            ticket_details = await helpdesk_backend.get_ticket_details(
                ticket_public_id=ticket.public_id,
            )
    except InvalidTicketTransitionError as exc:
        await response_message.answer(str(exc))
        return
    except RuntimeError:
        await response_message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    if ticket_details is None:
        await response_message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await context.ticket_live_session_store.refresh_session(
        ticket_public_id=str(ticket.public_id),
        client_chat_id=initial_command.client_chat_id,
        operator_telegram_user_id=ticket_details.assigned_operator_telegram_user_id,
    )

    context.logger.info(
        (
            "Client intake submission processed "
            "client_chat_id=%s ticket=%s created=%s has_follow_up=%s follow_up_recorded=%s"
        ),
        initial_command.client_chat_id,
        ticket.public_number,
        ticket.created,
        follow_up_command is not None,
        follow_up_recorded,
    )

    if ticket.created:
        await _publish_new_ticket_event(
            context=context,
            ticket_id=str(ticket.public_id),
            client_chat_id=initial_command.client_chat_id,
            subject=ticket_details.subject,
            public_number=ticket.public_number,
        )
        await response_message.answer(
            (
                build_ticket_created_text(ticket.public_number)
                if follow_up_recorded
                else build_ticket_created_with_missing_follow_up_text(ticket.public_number)
            ),
            reply_markup=build_client_ticket_markup(ticket_public_id=ticket.public_id),
        )
        return

    await response_message.answer(
        (
            build_ticket_message_added_text(
                ticket.public_number,
                operator_connected=ticket_details.assigned_operator_telegram_user_id is not None,
            )
            if follow_up_recorded
            else build_ticket_message_added_with_missing_follow_up_text(
                ticket.public_number,
                operator_connected=ticket_details.assigned_operator_telegram_user_id is not None,
            )
        ),
        reply_markup=build_client_ticket_markup(ticket_public_id=ticket.public_id),
    )


async def _publish_new_ticket_event(
    *,
    context: TicketRuntimeContext,
    ticket_id: str,
    client_chat_id: int,
    subject: str,
    public_number: str,
) -> None:
    try:
        await context.ticket_stream_publisher.publish_new_ticket(
            ticket_id=ticket_id,
            client_chat_id=client_chat_id,
            subject=subject,
        )
    except (ConnectionError, OSError, RuntimeError, TimeoutError) as exc:
        context.logger.warning(
            "New ticket stream publish failed ticket=%s client_chat_id=%s error=%s",
            public_number,
            client_chat_id,
            exc,
        )
