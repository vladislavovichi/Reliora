from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from aiogram.types import ReplyKeyboardMarkup

from application.services.diagnostics import DiagnosticsCheck, DiagnosticsReport
from application.use_cases.tickets.archive_browser import ArchiveCategoryFilter
from application.use_cases.tickets.summaries import (
    HistoricalTicketSummary,
    QueuedTicketSummary,
    TicketDetailsSummary,
    TicketMessageSummary,
)
from bot.formatters.operator_archive_views import format_archive_page, format_archive_topic_picker
from bot.formatters.operator_ticket_views import (
    format_active_ticket_context,
    format_queue_page,
    format_ticket_details,
    format_ticket_export_actions,
    format_ticket_history_chunks,
    format_ticket_more_actions,
)
from bot.formatters.system import build_help_text, build_start_text, format_diagnostics_report
from bot.keyboards.inline.client_actions import (
    build_client_ticket_finish_confirmation_markup,
)
from bot.keyboards.inline.feedback import (
    build_ticket_feedback_comment_markup,
    build_ticket_feedback_rating_markup,
)
from bot.keyboards.inline.macros import (
    build_operator_macro_picker_markup,
    build_operator_macro_preview_markup,
)
from bot.keyboards.inline.operator_actions import (
    build_queue_markup,
    build_ticket_actions_markup,
    build_ticket_export_actions_markup,
    build_ticket_more_actions_markup,
)
from bot.keyboards.inline.operator_history import build_archive_topic_picker_markup
from bot.keyboards.inline.tags import build_ticket_tags_markup
from bot.keyboards.reply.main_menu import build_main_menu
from bot.texts.buttons import (
    ARCHIVE_BUTTON_TEXT,
    BACK_BUTTON_TEXT,
    BACK_TO_TICKET_BUTTON_TEXT,
    CANCEL_BUTTON_TEXT,
    CATEGORIES_BUTTON_TEXT,
    COMMENT_BUTTON_TEXT,
    HELP_BUTTON_TEXT,
    MACROS_BUTTON_TEXT,
    MY_TICKETS_BUTTON_TEXT,
    OPERATORS_BUTTON_TEXT,
    QUEUE_BUTTON_TEXT,
    SKIP_BUTTON_TEXT,
    STATS_BUTTON_TEXT,
    TAKE_NEXT_BUTTON_TEXT,
)
from domain.enums.roles import UserRole
from domain.enums.tickets import TicketMessageSenderType, TicketStatus


def test_build_start_text_for_user_stays_user_friendly() -> None:
    result = build_start_text(UserRole.USER)

    assert "Поддержка в Telegram." in result
    assert "выберите тему обращения" in result.lower()
    assert "оператор" not in result
    assert "суперадминистратор" not in result


def test_build_start_text_for_super_admin_mentions_admin_scope() -> None:
    result = build_start_text(UserRole.SUPER_ADMIN)

    assert "Панель суперадминистратора." in result
    assert "операторы, макросы и темы" in result


def test_build_help_text_for_user_does_not_expose_operator_commands() -> None:
    result = build_help_text(UserRole.USER)

    assert "/start - открыть меню заново" in result
    assert "/help - показать краткую справку" in result
    assert "/queue" not in result
    assert "/operators" not in result


def test_build_help_text_for_operator_is_menu_first() -> None:
    result = build_help_text(UserRole.OPERATOR)

    assert "Навигация" in result
    assert f"«{QUEUE_BUTTON_TEXT}» - открыть новые заявки." in result
    assert f"«{MY_TICKETS_BUTTON_TEXT}» - вернуться к активным диалогам." in result
    assert "/start - открыть меню заново" in result
    assert "/health" not in result
    assert "/ticket" not in result
    assert "/operators" not in result


def test_build_help_text_for_super_admin_is_menu_first() -> None:
    result = build_help_text(UserRole.SUPER_ADMIN)

    assert f"«{OPERATORS_BUTTON_TEXT}» - открыть состав команды и управление ролями." in result
    assert f"«{MACROS_BUTTON_TEXT}» - открыть библиотеку и редактирование макросов." in result
    assert f"«{CATEGORIES_BUTTON_TEXT}» - настроить темы новых обращений." in result
    assert "/add_operator" not in result
    assert "/remove_operator" not in result
    assert "/health" not in result


def test_build_main_menu_for_user_is_minimal() -> None:
    keyboard = build_main_menu(UserRole.USER)

    assert _keyboard_rows(keyboard) == ((HELP_BUTTON_TEXT,),)
    assert keyboard.input_field_placeholder == "Сообщение в поддержку"


def test_build_main_menu_for_operator_contains_operator_navigation() -> None:
    keyboard = build_main_menu(UserRole.OPERATOR)

    assert _keyboard_rows(keyboard) == (
        (QUEUE_BUTTON_TEXT, MY_TICKETS_BUTTON_TEXT),
        (ARCHIVE_BUTTON_TEXT, STATS_BUTTON_TEXT),
        (TAKE_NEXT_BUTTON_TEXT,),
        (HELP_BUTTON_TEXT, CANCEL_BUTTON_TEXT),
    )
    assert keyboard.input_field_placeholder == "Главное меню"


def test_build_main_menu_for_super_admin_contains_admin_navigation() -> None:
    keyboard = build_main_menu(UserRole.SUPER_ADMIN)

    assert _keyboard_rows(keyboard) == (
        (QUEUE_BUTTON_TEXT, MY_TICKETS_BUTTON_TEXT),
        (ARCHIVE_BUTTON_TEXT, STATS_BUTTON_TEXT),
        (TAKE_NEXT_BUTTON_TEXT,),
        (OPERATORS_BUTTON_TEXT, MACROS_BUTTON_TEXT),
        (CATEGORIES_BUTTON_TEXT,),
        (HELP_BUTTON_TEXT, CANCEL_BUTTON_TEXT),
    )
    assert keyboard.input_field_placeholder == "Главное меню"


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
    assert "   В очереди • высокий приоритет" in result
    assert "   Не приходит письмо" in result
    assert "Откройте заявку, чтобы посмотреть историю и действия." in result


def test_format_archive_page_returns_case_list_with_mini_titles() -> None:
    tickets = (
        HistoricalTicketSummary(
            public_id=uuid4(),
            public_number="HD-ARCH0001",
            status=TicketStatus.CLOSED,
            created_at=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
            closed_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
            mini_title="Не могу войти в кабинет после смены пароля",
            category_id=2,
            category_title="Доступ и вход",
        ),
    )

    result = format_archive_page(
        tickets,
        current_page=1,
        total_pages=2,
        selected_category_title="Доступ и вход",
        total_filtered_tickets=1,
    )

    assert "Архив · Доступ и вход" in result
    assert "Дела: 1 · страница 1 / 2" in result
    assert "1. HD-ARCH0001 · Доступ и вход" in result
    assert "Закрыта • Создана" in result
    assert "Не могу войти в кабинет после смены пароля" in result


def test_format_archive_topic_picker_lists_available_topics() -> None:
    result = format_archive_topic_picker(
        filters=(
            ArchiveCategoryFilter(id=0, title="Все темы", ticket_count=6),
            ArchiveCategoryFilter(id=2, title="Доступ и вход", ticket_count=4),
            ArchiveCategoryFilter(id=3, title="Оплата", ticket_count=2),
        ),
        selected_category_title="Доступ и вход",
    )

    assert "Темы архива" in result
    assert "Сейчас выбрано: Доступ и вход" in result
    assert "1. Доступ и вход · 4" in result
    assert "2. Оплата · 2" in result


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
        category_title="Доступ и вход",
        tags=("billing", "vip"),
        last_message_text="Проблема началась после смены пароля и теперь доступ не работает.",
        last_message_sender_type=TicketMessageSenderType.CLIENT,
        message_history=(),
    )

    result = format_ticket_details(ticket)

    assert "Заявка HD-AAAA1111" in result
    assert "В работе • высокий приоритет" in result
    assert "\nТема\nНе могу войти в личный кабинет" in result
    assert "\nКатегория\nДоступ и вход" in result
    assert "\nОператор\nИван Петров" in result
    assert "\nСоздана\n07.04.2026 12:30 UTC" in result
    assert "\nТеги\nbilling, vip" in result
    assert "\nПоследнее сообщение\nКлиент — Проблема началась после смены пароля" in result


def test_build_ticket_actions_markup_adds_macro_action_for_active_ticket() -> None:
    markup = build_ticket_actions_markup(ticket_public_id=uuid4(), status=TicketStatus.ASSIGNED)
    rows = tuple(tuple(button.text for button in row) for row in markup.inline_keyboard)

    assert rows == (("Закрыть", "Макросы"), ("Экспорт", "Ещё"))


def test_build_ticket_actions_markup_hides_transfer_for_queued_ticket() -> None:
    markup = build_ticket_actions_markup(ticket_public_id=uuid4(), status=TicketStatus.QUEUED)
    rows = tuple(tuple(button.text for button in row) for row in markup.inline_keyboard)

    assert ("Взять", "Экспорт") in rows
    assert all("Передать" not in row for row in rows)


def test_build_ticket_more_actions_markup_groups_secondary_actions() -> None:
    markup = build_ticket_more_actions_markup(
        ticket_public_id=uuid4(),
        status=TicketStatus.ASSIGNED,
    )
    rows = tuple(tuple(button.text for button in row) for row in markup.inline_keyboard)

    assert rows == (
        ("Метки", "Передать"),
        ("Заметки",),
        ("Экспорт",),
        ("Эскалация", "Карточка"),
        ("Назад",),
    )


def test_build_ticket_export_actions_markup_offers_two_formats() -> None:
    markup = build_ticket_export_actions_markup(ticket_public_id=uuid4())
    rows = tuple(tuple(button.text for button in row) for row in markup.inline_keyboard)

    assert rows == (("HTML отчёт", "CSV выгрузка"), ("Назад",))


def test_build_archive_topic_picker_markup_keeps_clean_return_path() -> None:
    markup = build_archive_topic_picker_markup(
        filters=(
            ArchiveCategoryFilter(id=0, title="Все темы", ticket_count=6),
            ArchiveCategoryFilter(id=2, title="Доступ и вход", ticket_count=4),
            ArchiveCategoryFilter(id=3, title="Оплата", ticket_count=2),
        ),
        current_page=2,
        selected_category_id=2,
    )
    rows = tuple(tuple(button.text for button in row) for row in markup.inline_keyboard)

    assert rows == (("• Доступ и вход · 4",), ("Оплата · 2",), ("К архиву",))


def test_build_client_ticket_finish_confirmation_markup_fits_telegram_callback_limit() -> None:
    markup = build_client_ticket_finish_confirmation_markup(ticket_public_id=uuid4())
    rows = tuple(tuple(button.text for button in row) for row in markup.inline_keyboard)

    assert rows == (("Завершить", CANCEL_BUTTON_TEXT),)


def test_build_ticket_feedback_rating_markup_stays_compact() -> None:
    markup = build_ticket_feedback_rating_markup(ticket_public_id=uuid4())
    rows = tuple(tuple(button.text for button in row) for row in markup.inline_keyboard)

    assert rows == (("1", "2", "3", "4", "5"),)


def test_build_ticket_feedback_comment_markup_keeps_clean_skip_path() -> None:
    markup = build_ticket_feedback_comment_markup(ticket_public_id=uuid4())
    rows = tuple(tuple(button.text for button in row) for row in markup.inline_keyboard)

    assert rows == ((COMMENT_BUTTON_TEXT, SKIP_BUTTON_TEXT),)


def test_build_ticket_tags_markup_uses_consistent_ticket_return_action() -> None:
    markup = build_ticket_tags_markup(
        ticket_public_id=uuid4(),
        available_tags=(),
        active_tag_names=(),
    )
    rows = tuple(tuple(button.text for button in row) for row in markup.inline_keyboard)

    assert rows == ((BACK_TO_TICKET_BUTTON_TEXT,),)


def test_build_operator_macro_navigation_is_consistent() -> None:
    markup = build_operator_macro_picker_markup(
        ticket_public_id=uuid4(),
        macros=(),
        current_page=1,
        total_pages=1,
    )
    picker_rows = tuple(tuple(button.text for button in row) for row in markup.inline_keyboard)
    preview_markup = build_operator_macro_preview_markup(
        ticket_public_id=uuid4(),
        macro_id=1,
        page=1,
    )
    preview_rows = tuple(
        tuple(button.text for button in row) for row in preview_markup.inline_keyboard
    )

    assert picker_rows == ((BACK_TO_TICKET_BUTTON_TEXT,),)
    assert preview_rows == (("Отправить", BACK_BUTTON_TEXT),)


def test_format_active_ticket_context_stays_compact_and_obvious() -> None:
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
        category_title="Доступ и вход",
        tags=("billing", "vip"),
        last_message_text="Проблема началась после смены пароля и теперь доступ не работает.",
        last_message_sender_type=TicketMessageSenderType.CLIENT,
        message_history=(),
    )

    result = format_active_ticket_context(ticket)

    assert result.startswith("Текущий диалог")
    assert "HD-AAAA1111 · В работе • высокий приоритет" in result
    assert "Не могу войти в личный кабинет" in result
    assert "Категория · Доступ и вход" in result
    assert "Оператор · Иван Петров" in result
    assert "Теги · billing, vip" in result


def test_format_ticket_more_actions_reads_like_structured_secondary_surface() -> None:
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
        message_history=(),
    )

    result = format_ticket_more_actions(ticket, is_active=True)

    assert result.startswith("Текущий диалог")
    assert "\nЕщё" in result
    assert "\nИзменить\nМетки · Передать" in result
    assert "\nОтчёт\nЭкспорт" in result
    assert "\nСтатус и детали\nЭскалация · Карточка" in result


def test_format_ticket_export_actions_reads_like_report_surface() -> None:
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
        tags=("vip",),
        last_message_text="Уже проверяем доступ.",
        last_message_sender_type=TicketMessageSenderType.OPERATOR,
        message_history=(),
    )

    result = format_ticket_export_actions(ticket, is_active=True)

    assert result.startswith("Текущий диалог")
    assert "\nЭкспорт" in result
    assert (
        "\nФорматы\nHTML отчёт — спокойный case file с карточкой, перепиской и материалами дела."
        in result
    )
    assert "\nCSV выгрузка — структурированный слой для анализа, handoff и сверки." in result
    assert "Обе выгрузки доступны сразу из этого экрана." in result


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
            DiagnosticsCheck(
                name="bootstrap",
                category="liveness",
                ok=True,
                detail="runtime инициализирован",
            ),
            DiagnosticsCheck(
                name="redis",
                category="dependency",
                ok=False,
                detail="RuntimeError: timeout",
            ),
        )
    )

    result = format_diagnostics_report(report)

    assert "Есть проблемы с готовностью сервиса." in result
    assert "- liveness: в порядке" in result
    assert "- readiness: ошибка" in result
    assert "- bootstrap: в порядке (runtime инициализирован)" in result
    assert "- redis: ошибка (RuntimeError: timeout)" in result


def _keyboard_rows(keyboard: ReplyKeyboardMarkup) -> tuple[tuple[str, ...], ...]:
    rows = keyboard.keyboard
    assert rows is not None
    return tuple(tuple(button.text for button in row) for row in rows)
