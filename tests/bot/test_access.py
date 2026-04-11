from __future__ import annotations

from application.services.authorization import Permission
from bot.access.policies import (
    PROTECTED_CALLBACK_PREFIX_PERMISSIONS,
    PROTECTED_COMMAND_PERMISSIONS,
    PROTECTED_MESSAGE_TEXT_PERMISSIONS,
    PROTECTED_STATE_PERMISSIONS,
    extract_command_name,
    resolve_required_permission,
)
from bot.texts.buttons import (
    ARCHIVE_BUTTON_TEXT,
    CATEGORIES_BUTTON_TEXT,
    HELP_BUTTON_TEXT,
    MACROS_BUTTON_TEXT,
    MY_TICKETS_BUTTON_TEXT,
    OPERATORS_BUTTON_TEXT,
    QUEUE_BUTTON_TEXT,
    STATS_BUTTON_TEXT,
    TAKE_NEXT_BUTTON_TEXT,
)


def test_extract_command_name_strips_bot_suffix_and_args() -> None:
    assert extract_command_name("/health@test_bot 123") == "health"


def test_resolve_required_permission_for_operator_command() -> None:
    result = resolve_required_permission(message_text="/health")

    assert result == Permission.ACCESS_OPERATOR


def test_resolve_required_permission_for_health_command() -> None:
    result = resolve_required_permission(message_text="/health")

    assert result == Permission.ACCESS_OPERATOR


def test_protected_command_permissions_cover_operator_commands() -> None:
    operator_commands = {
        command_name
        for command_name, permission in PROTECTED_COMMAND_PERMISSIONS.items()
        if permission == Permission.ACCESS_OPERATOR
    }

    assert operator_commands == {
        "health",
    }


def test_protected_command_permissions_cover_admin_commands() -> None:
    admin_commands = {
        command_name
        for command_name, permission in PROTECTED_COMMAND_PERMISSIONS.items()
        if permission == Permission.MANAGE_OPERATORS
    }

    assert admin_commands == set()


def test_protected_message_permissions_cover_navigation_buttons() -> None:
    assert PROTECTED_MESSAGE_TEXT_PERMISSIONS[QUEUE_BUTTON_TEXT] == Permission.ACCESS_OPERATOR
    assert PROTECTED_MESSAGE_TEXT_PERMISSIONS[ARCHIVE_BUTTON_TEXT] == Permission.ACCESS_OPERATOR
    assert PROTECTED_MESSAGE_TEXT_PERMISSIONS[OPERATORS_BUTTON_TEXT] == Permission.MANAGE_OPERATORS
    assert PROTECTED_MESSAGE_TEXT_PERMISSIONS[MACROS_BUTTON_TEXT] == Permission.MANAGE_OPERATORS
    assert PROTECTED_MESSAGE_TEXT_PERMISSIONS[CATEGORIES_BUTTON_TEXT] == Permission.MANAGE_OPERATORS


def test_protected_callback_permissions_cover_operator_and_admin_prefixes() -> None:
    assert ("operator:", Permission.ACCESS_OPERATOR) in PROTECTED_CALLBACK_PREFIX_PERMISSIONS
    assert ("operator_queue:", Permission.ACCESS_OPERATOR) in PROTECTED_CALLBACK_PREFIX_PERMISSIONS
    assert ("operator_macro:", Permission.ACCESS_OPERATOR) in PROTECTED_CALLBACK_PREFIX_PERMISSIONS
    assert (
        "operator_archive:",
        Permission.ACCESS_OPERATOR,
    ) in PROTECTED_CALLBACK_PREFIX_PERMISSIONS
    assert ("operator_stats:", Permission.ACCESS_OPERATOR) in PROTECTED_CALLBACK_PREFIX_PERMISSIONS
    assert (
        "operator_stats_export:",
        Permission.ACCESS_OPERATOR,
    ) in PROTECTED_CALLBACK_PREFIX_PERMISSIONS
    assert ("operator_tag:", Permission.ACCESS_OPERATOR) in PROTECTED_CALLBACK_PREFIX_PERMISSIONS
    assert ("admin_category:", Permission.MANAGE_OPERATORS) in PROTECTED_CALLBACK_PREFIX_PERMISSIONS
    assert ("admin_macro:", Permission.MANAGE_OPERATORS) in PROTECTED_CALLBACK_PREFIX_PERMISSIONS
    assert ("admin_operator:", Permission.MANAGE_OPERATORS) in PROTECTED_CALLBACK_PREFIX_PERMISSIONS


def test_protected_state_permissions_cover_operator_fsm_states() -> None:
    assert (
        PROTECTED_STATE_PERMISSIONS["OperatorTicketStates:reassigning"]
        == Permission.ACCESS_OPERATOR
    )
    assert (
        PROTECTED_STATE_PERMISSIONS["AdminOperatorStates:adding_operator"]
        == Permission.MANAGE_OPERATORS
    )
    assert (
        PROTECTED_STATE_PERMISSIONS["AdminCategoryStates:creating_title"]
        == Permission.MANAGE_OPERATORS
    )
    assert (
        PROTECTED_STATE_PERMISSIONS["AdminCategoryStates:editing_title"]
        == Permission.MANAGE_OPERATORS
    )
    assert (
        PROTECTED_STATE_PERMISSIONS["AdminMacroStates:creating_title"]
        == Permission.MANAGE_OPERATORS
    )
    assert (
        PROTECTED_STATE_PERMISSIONS["AdminMacroStates:creating_body"] == Permission.MANAGE_OPERATORS
    )
    assert (
        PROTECTED_STATE_PERMISSIONS["AdminMacroStates:creating_preview"]
        == Permission.MANAGE_OPERATORS
    )
    assert (
        PROTECTED_STATE_PERMISSIONS["AdminMacroStates:editing_title"] == Permission.MANAGE_OPERATORS
    )
    assert (
        PROTECTED_STATE_PERMISSIONS["AdminMacroStates:editing_body"] == Permission.MANAGE_OPERATORS
    )


def test_resolve_required_permission_for_operator_navigation_button() -> None:
    result = resolve_required_permission(message_text=QUEUE_BUTTON_TEXT)

    assert result == Permission.ACCESS_OPERATOR


def test_resolve_required_permission_for_take_navigation_button() -> None:
    result = resolve_required_permission(message_text=TAKE_NEXT_BUTTON_TEXT)

    assert result == Permission.ACCESS_OPERATOR


def test_resolve_required_permission_for_my_tickets_navigation_button() -> None:
    result = resolve_required_permission(message_text=MY_TICKETS_BUTTON_TEXT)

    assert result == Permission.ACCESS_OPERATOR


def test_resolve_required_permission_for_archive_navigation_button() -> None:
    result = resolve_required_permission(message_text=ARCHIVE_BUTTON_TEXT)

    assert result == Permission.ACCESS_OPERATOR


def test_resolve_required_permission_for_stats_navigation_button() -> None:
    result = resolve_required_permission(message_text=STATS_BUTTON_TEXT)

    assert result == Permission.ACCESS_OPERATOR


def test_resolve_required_permission_for_operator_callback() -> None:
    result = resolve_required_permission(
        callback_data="operator:take:ticket-public-id",
    )

    assert result == Permission.ACCESS_OPERATOR


def test_resolve_required_permission_for_operator_state() -> None:
    result = resolve_required_permission(
        state_name="OperatorTicketStates:reassigning",
    )

    assert result == Permission.ACCESS_OPERATOR


def test_resolve_required_permission_returns_none_for_regular_help() -> None:
    result = resolve_required_permission(message_text=HELP_BUTTON_TEXT)

    assert result is None


def test_resolve_required_permission_for_super_admin_navigation_button() -> None:
    result = resolve_required_permission(message_text=OPERATORS_BUTTON_TEXT)

    assert result == Permission.MANAGE_OPERATORS


def test_resolve_required_permission_for_super_admin_macro_navigation_button() -> None:
    result = resolve_required_permission(message_text=MACROS_BUTTON_TEXT)

    assert result == Permission.MANAGE_OPERATORS


def test_resolve_required_permission_for_super_admin_category_navigation_button() -> None:
    result = resolve_required_permission(message_text=CATEGORIES_BUTTON_TEXT)

    assert result == Permission.MANAGE_OPERATORS


def test_resolve_required_permission_for_super_admin_callback() -> None:
    result = resolve_required_permission(
        callback_data="admin_operator:revoke:1001",
    )

    assert result == Permission.MANAGE_OPERATORS


def test_resolve_required_permission_for_super_admin_macro_callback() -> None:
    result = resolve_required_permission(
        callback_data="admin_macro:view:7:1",
    )

    assert result == Permission.MANAGE_OPERATORS


def test_resolve_required_permission_for_super_admin_category_callback() -> None:
    result = resolve_required_permission(
        callback_data="admin_category:view:7:1",
    )

    assert result == Permission.MANAGE_OPERATORS
