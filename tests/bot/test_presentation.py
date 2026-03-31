from __future__ import annotations

from aiogram.types import ReplyKeyboardMarkup

from bot.formatters.system import build_help_text, build_start_text
from bot.keyboards.reply.main_menu import build_main_menu
from bot.texts.buttons import (
    ADD_OPERATOR_BUTTON_TEXT,
    CANCEL_BUTTON_TEXT,
    HELP_BUTTON_TEXT,
    OPERATORS_BUTTON_TEXT,
    QUEUE_BUTTON_TEXT,
    REMOVE_OPERATOR_BUTTON_TEXT,
    STATS_BUTTON_TEXT,
    TAKE_NEXT_BUTTON_TEXT,
)
from domain.enums.roles import UserRole


def test_build_start_text_for_user_stays_user_friendly() -> None:
    result = build_start_text(UserRole.USER)

    assert "бот поддержки" in result
    assert "Просто отправьте сообщение" in result
    assert "оператор" not in result
    assert "супер администратор" not in result


def test_build_start_text_for_super_admin_mentions_admin_scope() -> None:
    result = build_start_text(UserRole.SUPER_ADMIN)

    assert "супер администратор" in result
    assert "управление операторами" in result


def test_build_help_text_for_user_does_not_expose_operator_commands() -> None:
    result = build_help_text(UserRole.USER)

    assert "/start - показать приветствие и главное меню" in result
    assert "/help - показать справку по доступным действиям" in result
    assert "/queue" not in result
    assert "/operators" not in result


def test_build_help_text_for_operator_includes_operator_commands_only() -> None:
    result = build_help_text(UserRole.OPERATOR)

    assert "/queue - показать ближайшие заявки в очереди" in result
    assert "/take - взять следующую заявку" in result
    assert "/stats - показать операционную статистику" in result
    assert "/operators" not in result


def test_build_help_text_for_super_admin_includes_admin_commands() -> None:
    result = build_help_text(UserRole.SUPER_ADMIN)

    assert "/queue - показать ближайшие заявки в очереди" in result
    assert "/operators - показать список операторов" in result
    assert "/add_operator <telegram_user_id> [display_name] - выдать права оператора" in result
    assert "/remove_operator <telegram_user_id> - снять права оператора" in result


def test_build_main_menu_for_user_is_minimal() -> None:
    keyboard = build_main_menu(UserRole.USER)

    assert _keyboard_rows(keyboard) == ((HELP_BUTTON_TEXT,),)


def test_build_main_menu_for_operator_contains_operator_navigation() -> None:
    keyboard = build_main_menu(UserRole.OPERATOR)

    assert _keyboard_rows(keyboard) == (
        (QUEUE_BUTTON_TEXT, TAKE_NEXT_BUTTON_TEXT),
        (STATS_BUTTON_TEXT, CANCEL_BUTTON_TEXT),
        (HELP_BUTTON_TEXT,),
    )


def test_build_main_menu_for_super_admin_contains_admin_navigation() -> None:
    keyboard = build_main_menu(UserRole.SUPER_ADMIN)

    assert _keyboard_rows(keyboard) == (
        (QUEUE_BUTTON_TEXT, TAKE_NEXT_BUTTON_TEXT),
        (STATS_BUTTON_TEXT, CANCEL_BUTTON_TEXT),
        (OPERATORS_BUTTON_TEXT,),
        (ADD_OPERATOR_BUTTON_TEXT, REMOVE_OPERATOR_BUTTON_TEXT),
        (HELP_BUTTON_TEXT,),
    )


def _keyboard_rows(keyboard: ReplyKeyboardMarkup) -> tuple[tuple[str, ...], ...]:
    rows = keyboard.keyboard
    assert rows is not None
    return tuple(tuple(button.text for button in row) for row in rows)
