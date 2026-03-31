from __future__ import annotations

from aiogram.types import CallbackQuery, Message

from application.services.authorization import Permission

OPERATOR_COMMANDS = frozenset(
    {
        "queue",
        "take",
        "ticket",
        "macros",
        "tags",
        "alltags",
        "addtag",
        "rmtag",
        "cancel",
        "stats",
    }
)
OPERATOR_CALLBACK_PREFIXES = frozenset({"operator:", "operator_macro:"})
OPERATOR_STATE_NAMES = frozenset(
    {
        "OperatorTicketStates:replying",
        "OperatorTicketStates:reassigning",
    }
)

OPERATOR_ACCESS_DENIED_MESSAGE = "Это действие доступно только операторам и супер администратору."
SUPER_ADMIN_ACCESS_DENIED_MESSAGE = "Это действие доступно только супер администратору."


def extract_command_name(text: str | None) -> str | None:
    if text is None:
        return None

    stripped = text.strip()
    if not stripped.startswith("/"):
        return None

    command_token = stripped.split(maxsplit=1)[0][1:]
    command_name = command_token.split("@", maxsplit=1)[0].lower()
    if not command_name:
        return None
    return command_name


def resolve_required_permission(
    *,
    message_text: str | None = None,
    callback_data: str | None = None,
    state_name: str | None = None,
) -> Permission | None:
    command_name = extract_command_name(message_text)
    if command_name in OPERATOR_COMMANDS:
        return Permission.ACCESS_OPERATOR

    if callback_data is not None and any(
        callback_data.startswith(prefix) for prefix in OPERATOR_CALLBACK_PREFIXES
    ):
        return Permission.ACCESS_OPERATOR

    if state_name in OPERATOR_STATE_NAMES:
        return Permission.ACCESS_OPERATOR

    return None


def get_permission_denied_message(permission: Permission) -> str:
    if permission == Permission.MANAGE_OPERATORS:
        return SUPER_ADMIN_ACCESS_DENIED_MESSAGE
    if permission == Permission.ACCESS_ADMIN:
        return SUPER_ADMIN_ACCESS_DENIED_MESSAGE
    return OPERATOR_ACCESS_DENIED_MESSAGE


async def deny_event_access(
    event: Message | CallbackQuery,
    *,
    permission: Permission,
) -> None:
    message_text = get_permission_denied_message(permission)
    if isinstance(event, CallbackQuery):
        await event.answer(message_text, show_alert=True)
        return

    await event.answer(message_text)
