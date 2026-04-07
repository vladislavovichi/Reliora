from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from aiogram.types import ReplyKeyboardMarkup

from application.services.diagnostics import DiagnosticsCheck, DiagnosticsReport
from application.use_cases.tickets.summaries import (
    QueuedTicketSummary,
    TicketDetailsSummary,
    TicketMessageSummary,
)
from bot.formatters.operator import (
    format_queue_page,
    format_ticket_details,
    format_ticket_history_chunks,
)
from bot.formatters.system import build_help_text, build_start_text, format_diagnostics_report
from bot.keyboards.inline.operator_actions import build_queue_markup
from bot.keyboards.reply.main_menu import build_main_menu
from bot.texts.buttons import (
    CANCEL_BUTTON_TEXT,
    HELP_BUTTON_TEXT,
    OPERATORS_BUTTON_TEXT,
    QUEUE_BUTTON_TEXT,
    STATS_BUTTON_TEXT,
    TAKE_NEXT_BUTTON_TEXT,
)
from domain.enums.roles import UserRole
from domain.enums.tickets import TicketMessageSenderType, TicketStatus


def test_build_start_text_for_user_stays_user_friendly() -> None:
    result = build_start_text(UserRole.USER)

    assert "Поддержка в Telegram." in result
    assert "Напишите сообщение" in result
    assert "оператор" not in result
    assert "суперадминистратор" not in result


def test_build_start_text_for_super_admin_mentions_admin_scope() -> None:
    result = build_start_text(UserRole.SUPER_ADMIN)

    assert "Рабочее меню суперадминистратора." in result
    assert "управление командой" in result


def test_build_help_text_for_user_does_not_expose_operator_commands() -> None:
    result = build_help_text(UserRole.USER)

    assert "/start - открыть главное меню" in result
    assert "/help - показать краткую справку" in result
    assert "/queue" not in result
    assert "/operators" not in result


def test_build_help_text_for_operator_includes_operator_commands_only() -> None:
    result = build_help_text(UserRole.OPERATOR)

    assert "/stats - открыть статистику" in result
    assert "/health - проверить состояние сервиса" in result
    assert "/ticket <ticket_public_id> - открыть карточку заявки" in result
    assert "/queue - " not in result
    assert "/take - " not in result
    assert "/operators" not in result


def test_build_help_text_for_super_admin_includes_admin_commands() -> None:
    result = build_help_text(UserRole.SUPER_ADMIN)

    assert "/health - проверить состояние сервиса" in result
    assert (
        "/add_operator <telegram_user_id> [display_name] - "
        "добавить оператора в команду"
    ) in result
    assert "/remove_operator <telegram_user_id> - снять роль оператора" in result
    assert "/queue - " not in result
    assert "/operators - " not in result


def test_build_main_menu_for_user_is_minimal() -> None:
    keyboard = build_main_menu(UserRole.USER)

    assert _keyboard_rows(keyboard) == ((HELP_BUTTON_TEXT,),)
    assert keyboard.input_field_placeholder == "Опишите вопрос одним сообщением"


def test_build_main_menu_for_operator_contains_operator_navigation() -> None:
    keyboard = build_main_menu(UserRole.OPERATOR)

    assert _keyboard_rows(keyboard) == (
        (QUEUE_BUTTON_TEXT, TAKE_NEXT_BUTTON_TEXT),
        (STATS_BUTTON_TEXT, CANCEL_BUTTON_TEXT),
        (HELP_BUTTON_TEXT,),
    )
    assert keyboard.input_field_placeholder == "Выберите раздел"


def test_build_main_menu_for_super_admin_contains_admin_navigation() -> None:
    keyboard = build_main_menu(UserRole.SUPER_ADMIN)

    assert _keyboard_rows(keyboard) == (
        (QUEUE_BUTTON_TEXT, TAKE_NEXT_BUTTON_TEXT),
        (STATS_BUTTON_TEXT, CANCEL_BUTTON_TEXT),
        (OPERATORS_BUTTON_TEXT,),
        (HELP_BUTTON_TEXT,),
    )
    assert keyboard.input_field_placeholder == "Выберите раздел"


def test_format_queue_page_returns_compact_paginated_text() -> None:
    tickets = (
        QueuedTicketSummary(
            public_id=uuid4(),
            public_number="HD-AAAA1111",
            subject="Нужен доступ к кабинету",
            priority="high",
            status=TicketStatus.QUEUED,
        ),
        QueuedTicketSummary(
            public_id=uuid4(),
            public_number="HD-BBBB2222",
            subject="Не приходит письмо",
            priority="normal",
            status=TicketStatus.QUEUED,
        ),
    )

    result = format_queue_page(tickets, current_page=2, total_pages=3)

    assert "Очередь" in result
    assert "Страница 2 / 3" in result
    assert "1. HD-AAAA1111" in result
    assert "   Высокий приоритет" in result
    assert "   Не приходит письмо" in result
    assert "Нажмите на заявку, чтобы открыть карточку." in result


def test_build_queue_markup_contains_ticket_actions_and_pagination() -> None:
    tickets = (
        QueuedTicketSummary(
            public_id=uuid4(),
            public_number="HD-AAAA1111",
            subject="Нужен доступ к кабинету",
            priority="high",
            status=TicketStatus.QUEUED,
        ),
        QueuedTicketSummary(
            public_id=uuid4(),
            public_number="HD-BBBB2222",
            subject="Не приходит письмо",
            priority="normal",
            status=TicketStatus.QUEUED,
        ),
    )

    markup = build_queue_markup(tickets=tickets, current_page=2, total_pages=4)
    rows = tuple(tuple(button.text for button in row) for row in markup.inline_keyboard)

    assert rows == (("HD-AAAA1111",), ("HD-BBBB2222",), ("‹ Назад", "2 / 4", "Далее ›"))


def test_format_ticket_details_returns_calm_operator_card() -> None:
    ticket = TicketDetailsSummary(
        public_id=uuid4(),
        public_number="HD-AAAA1111",
        client_chat_id=1001,
        status=TicketStatus.ASSIGNED,
        priority="high",
        subject="Не могу войти в личный кабинет",
        assigned_operator_id=7,
        assigned_operator_name="Иван Петров",
        assigned_operator_telegram_user_id=1001,
        created_at=datetime(2026, 4, 7, 12, 30, tzinfo=UTC),
        tags=("billing", "vip"),
        last_message_text="Проблема началась после смены пароля и теперь доступ не работает.",
        last_message_sender_type=TicketMessageSenderType.CLIENT,
        message_history=(),
    )

    result = format_ticket_details(ticket)

    assert "Заявка HD-AAAA1111" in result
    assert "В работе • высокий приоритет" in result
    assert "\nТема\nНе могу войти в личный кабинет" in result
    assert "\nОператор\nИван Петров" in result
    assert "\nСоздана\n07.04.2026 12:30 UTC" in result
    assert "\nТеги\nbilling, vip" in result
    assert "\nПоследнее сообщение\nКлиент — Проблема началась после смены пароля" in result


def test_format_ticket_history_chunks_returns_calm_conversation_blocks() -> None:
    ticket = TicketDetailsSummary(
        public_id=uuid4(),
        public_number="HD-AAAA1111",
        client_chat_id=1001,
        status=TicketStatus.ASSIGNED,
        priority="high",
        subject="Не могу войти в личный кабинет",
        assigned_operator_id=7,
        assigned_operator_name="Иван Петров",
        assigned_operator_telegram_user_id=1001,
        created_at=datetime(2026, 4, 7, 12, 30, tzinfo=UTC),
        tags=(),
        last_message_text="Уже проверяем доступ.",
        last_message_sender_type=TicketMessageSenderType.OPERATOR,
        message_history=(
            TicketMessageSummary(
                sender_type=TicketMessageSenderType.CLIENT,
                sender_operator_id=None,
                sender_operator_name=None,
                text="Не могу войти в личный кабинет.",
                created_at=datetime(2026, 4, 7, 12, 31, tzinfo=UTC),
            ),
            TicketMessageSummary(
                sender_type=TicketMessageSenderType.OPERATOR,
                sender_operator_id=7,
                sender_operator_name="Иван Петров",
                text="Уже проверяем доступ.",
                created_at=datetime(2026, 4, 7, 12, 35, tzinfo=UTC),
            ),
        ),
    )

    result = format_ticket_history_chunks(ticket)

    assert result[0].startswith("Переписка")
    assert "Клиент · 07.04.2026 12:31 UTC\nНе могу войти в личный кабинет." in result[0]
    assert "Оператор Иван Петров · 07.04.2026 12:35 UTC\nУже проверяем доступ." in result[0]


def test_format_diagnostics_report_uses_compact_russian_output() -> None:
    report = DiagnosticsReport(
        checks=(
            DiagnosticsCheck(name="bootstrap", ok=True, detail="runtime инициализирован"),
            DiagnosticsCheck(name="redis", ok=False, detail="RuntimeError: timeout"),
        )
    )

    result = format_diagnostics_report(report)

    assert "Есть проблемы с сервисом." in result
    assert "- bootstrap: в порядке (runtime инициализирован)" in result
    assert "- redis: ошибка (RuntimeError: timeout)" in result


def _keyboard_rows(keyboard: ReplyKeyboardMarkup) -> tuple[tuple[str, ...], ...]:
    rows = keyboard.keyboard
    assert rows is not None
    return tuple(tuple(button.text for button in row) for row in rows)
