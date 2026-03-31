from __future__ import annotations

from application.services.authorization import Permission
from bot.access import extract_command_name, resolve_required_permission
from bot.presentation import ADD_OPERATOR_BUTTON_TEXT, QUEUE_BUTTON_TEXT


def test_extract_command_name_strips_bot_suffix_and_args() -> None:
    assert extract_command_name("/queue@test_bot 123") == "queue"


def test_resolve_required_permission_for_operator_command() -> None:
    result = resolve_required_permission(message_text="/take")

    assert result == Permission.ACCESS_OPERATOR


def test_resolve_required_permission_for_operator_navigation_button() -> None:
    result = resolve_required_permission(message_text=QUEUE_BUTTON_TEXT)

    assert result == Permission.ACCESS_OPERATOR


def test_resolve_required_permission_for_operator_callback() -> None:
    result = resolve_required_permission(
        callback_data="operator:take:ticket-public-id",
    )

    assert result == Permission.ACCESS_OPERATOR


def test_resolve_required_permission_for_operator_state() -> None:
    result = resolve_required_permission(
        state_name="OperatorTicketStates:replying",
    )

    assert result == Permission.ACCESS_OPERATOR


def test_resolve_required_permission_returns_none_for_regular_help() -> None:
    result = resolve_required_permission(message_text="/help")

    assert result is None


def test_resolve_required_permission_for_super_admin_command() -> None:
    result = resolve_required_permission(message_text="/operators")

    assert result == Permission.MANAGE_OPERATORS


def test_resolve_required_permission_for_super_admin_navigation_button() -> None:
    result = resolve_required_permission(message_text=ADD_OPERATOR_BUTTON_TEXT)

    assert result == Permission.MANAGE_OPERATORS


def test_resolve_required_permission_for_super_admin_callback() -> None:
    result = resolve_required_permission(
        callback_data="admin_operator:revoke:1001",
    )

    assert result == Permission.MANAGE_OPERATORS
