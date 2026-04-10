from __future__ import annotations

from uuid import UUID

from aiogram.types import Message, User

from application.contracts.actors import OperatorIdentity, RequestActor
from application.contracts.tickets import (
    AddInternalNoteCommand,
    ApplyMacroToTicketCommand,
    AssignNextQueuedTicketCommand,
    ClientTicketMessageCommand,
    OperatorTicketReplyCommand,
    TicketAssignmentCommand,
)
from bot.handlers.common.ticket_attachments import IncomingTicketContent
from domain.entities.ticket import TicketAttachmentDetails


def build_request_actor(user: User | None) -> RequestActor | None:
    if user is None:
        return None
    return RequestActor(telegram_user_id=user.id)


def build_request_actor_from_id(telegram_user_id: int | None) -> RequestActor | None:
    if telegram_user_id is None:
        return None
    return RequestActor(telegram_user_id=telegram_user_id)


def build_operator_identity(user: User | None) -> OperatorIdentity | None:
    if user is None:
        return None
    return OperatorIdentity(
        telegram_user_id=user.id,
        display_name=user.full_name,
        username=user.username,
    )


def build_operator_identity_from_parts(
    *,
    telegram_user_id: int,
    display_name: str,
    username: str | None = None,
) -> OperatorIdentity:
    return OperatorIdentity(
        telegram_user_id=telegram_user_id,
        display_name=display_name,
        username=username,
    )


def build_client_ticket_message_command(
    *,
    message: Message,
    content: IncomingTicketContent,
    category_id: int | None = None,
) -> ClientTicketMessageCommand:
    return build_client_ticket_message_command_from_values(
        client_chat_id=message.chat.id,
        telegram_message_id=message.message_id,
        text=content.text,
        attachment=content.attachment,
        category_id=category_id,
    )


def build_client_ticket_message_command_from_values(
    *,
    client_chat_id: int,
    telegram_message_id: int,
    text: str | None,
    attachment: TicketAttachmentDetails | None,
    category_id: int | None = None,
) -> ClientTicketMessageCommand:
    return ClientTicketMessageCommand(
        client_chat_id=client_chat_id,
        telegram_message_id=telegram_message_id,
        text=text,
        attachment=attachment,
        category_id=category_id,
    )


def build_ticket_assignment_command(
    *,
    ticket_public_id: UUID,
    operator: OperatorIdentity,
) -> TicketAssignmentCommand:
    return TicketAssignmentCommand(
        ticket_public_id=ticket_public_id,
        operator=operator,
    )


def build_assign_next_ticket_command(
    *,
    operator: OperatorIdentity,
    prioritize_priority: bool = False,
) -> AssignNextQueuedTicketCommand:
    return AssignNextQueuedTicketCommand(
        operator=operator,
        prioritize_priority=prioritize_priority,
    )


def build_operator_reply_command(
    *,
    ticket_public_id: UUID,
    operator: OperatorIdentity,
    message: Message,
    content: IncomingTicketContent,
) -> OperatorTicketReplyCommand:
    return OperatorTicketReplyCommand(
        ticket_public_id=ticket_public_id,
        operator=operator,
        telegram_message_id=message.message_id,
        text=content.text,
        attachment=content.attachment,
    )


def build_internal_note_command(
    *,
    ticket_public_id: UUID,
    author: OperatorIdentity,
    text: str,
) -> AddInternalNoteCommand:
    return AddInternalNoteCommand(
        ticket_public_id=ticket_public_id,
        author=author,
        text=text,
    )


def build_apply_macro_command(
    *,
    ticket_public_id: UUID,
    macro_id: int,
    operator: OperatorIdentity,
) -> ApplyMacroToTicketCommand:
    return ApplyMacroToTicketCommand(
        ticket_public_id=ticket_public_id,
        macro_id=macro_id,
        operator=operator,
    )
