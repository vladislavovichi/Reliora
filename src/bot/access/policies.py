from __future__ import annotations

from collections.abc import Mapping

from application.services.authorization import Permission
from bot.texts.buttons import OPERATOR_NAVIGATION_BUTTONS, SUPER_ADMIN_NAVIGATION_BUTTONS

PROTECTED_COMMAND_PERMISSIONS: Mapping[str, Permission] = {
    "queue": Permission.ACCESS_OPERATOR,
    "take": Permission.ACCESS_OPERATOR,
    "ticket": Permission.ACCESS_OPERATOR,
    "health": Permission.ACCESS_OPERATOR,
    "macros": Permission.ACCESS_OPERATOR,
    "tags": Permission.ACCESS_OPERATOR,
    "alltags": Permission.ACCESS_OPERATOR,
    "addtag": Permission.ACCESS_OPERATOR,
    "rmtag": Permission.ACCESS_OPERATOR,
    "cancel": Permission.ACCESS_OPERATOR,
    "stats": Permission.ACCESS_OPERATOR,
    "operators": Permission.MANAGE_OPERATORS,
    "add_operator": Permission.MANAGE_OPERATORS,
    "remove_operator": Permission.MANAGE_OPERATORS,
}
PROTECTED_MESSAGE_TEXT_PERMISSIONS: Mapping[str, Permission] = {
    **{button_text: Permission.ACCESS_OPERATOR for button_text in OPERATOR_NAVIGATION_BUTTONS},
    **{button_text: Permission.MANAGE_OPERATORS for button_text in SUPER_ADMIN_NAVIGATION_BUTTONS},
}
PROTECTED_CALLBACK_PREFIX_PERMISSIONS: tuple[tuple[str, Permission], ...] = (
    ("admin_operator:", Permission.MANAGE_OPERATORS),
    ("operator:", Permission.ACCESS_OPERATOR),
    ("operator_queue:", Permission.ACCESS_OPERATOR),
    ("operator_macro:", Permission.ACCESS_OPERATOR),
)
PROTECTED_STATE_PERMISSIONS: Mapping[str, Permission] = {
    "OperatorTicketStates:replying": Permission.ACCESS_OPERATOR,
    "OperatorTicketStates:reassigning": Permission.ACCESS_OPERATOR,
}


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
    if command_name is not None:
        permission = PROTECTED_COMMAND_PERMISSIONS.get(command_name)
        if permission is not None:
            return permission

    if message_text is not None:
        permission = PROTECTED_MESSAGE_TEXT_PERMISSIONS.get(message_text)
        if permission is not None:
            return permission

    if callback_data is not None:
        for callback_prefix, permission in PROTECTED_CALLBACK_PREFIX_PERMISSIONS:
            if callback_data.startswith(callback_prefix):
                return permission

    if state_name is not None:
        permission = PROTECTED_STATE_PERMISSIONS.get(state_name)
        if permission is not None:
            return permission

    return None
