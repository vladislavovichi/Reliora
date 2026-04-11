from __future__ import annotations

from collections.abc import Sequence

from application.use_cases.tickets.archive_browser import ArchiveCategoryFilter
from application.use_cases.tickets.summaries import HistoricalTicketSummary, TicketDetailsSummary
from bot.formatters.operator_primitives import format_status, format_timestamp, shorten_text

ARCHIVE_PAGE_CHUNK = 6


def format_archive_page(
    tickets: Sequence[HistoricalTicketSummary],
    *,
    current_page: int,
    total_pages: int,
    selected_category_title: str | None = None,
    total_filtered_tickets: int | None = None,
) -> str:
    title = "Архив"
    if selected_category_title:
        title = f"Архив · {selected_category_title}"

    lines = [title]
    if total_filtered_tickets is not None:
        lines.append(f"Дела: {total_filtered_tickets} · страница {current_page} / {total_pages}")
    else:
        lines.append(f"Страница {current_page} / {total_pages}")
    lines.extend(["", "Закрытые дела с быстрым доступом к карточке и экспорту."])

    if not tickets:
        lines.extend(
            [
                "",
                "По выбранной теме архив пока пуст.",
                "Откройте все темы или выберите другое направление.",
            ]
        )
        return "\n".join(lines)

    for index, ticket in enumerate(tickets, start=1):
        lines.extend(
            [
                "",
                f"{index}. {_build_archive_ticket_heading(ticket)}",
                f"   {shorten_text(ticket.mini_title, 96)}",
                f"   {_build_archive_meta(ticket)}",
            ]
        )

    lines.extend(
        [
            "",
            "Откройте дело ниже, чтобы посмотреть переписку, материалы и выгрузить отчёт.",
        ]
    )
    return "\n".join(lines)


def format_archive_topic_picker(
    *,
    filters: Sequence[ArchiveCategoryFilter],
    selected_category_title: str | None,
) -> str:
    lines = [
        "Темы архива",
        "",
        (
            f"Сейчас выбрано: {selected_category_title}"
            if selected_category_title is not None
            else "Сейчас выбрано: все темы"
        ),
        "",
        "Выберите направление и вернитесь к списку закрытых дел.",
    ]
    if len(filters) <= 1:
        lines.extend(["", "Отдельных тем в архиве пока нет."])
        return "\n".join(lines)

    for index, category_filter in enumerate(
        (item for item in filters if item.id != 0),
        start=1,
    ):
        lines.append(f"{index}. {category_filter.title} · {category_filter.ticket_count}")
    return "\n".join(lines)


def format_archived_ticket_surface(ticket: TicketDetailsSummary) -> str:
    lines = [
        f"Архивное дело {ticket.public_number}",
        "",
        "Состояние",
        format_status(ticket.status).capitalize(),
        "",
        "Обращение",
        ticket.subject,
    ]
    if ticket.category_title:
        lines.extend(["", "Тема", ticket.category_title])
    lines.extend(
        [
            "",
            "Период",
            _build_ticket_period(ticket),
        ]
    )
    if ticket.assigned_operator_name:
        lines.extend(["", "Ответственный", ticket.assigned_operator_name])
    if ticket.tags:
        lines.extend(["", "Теги", ", ".join(ticket.tags)])
    lines.extend(
        [
            "",
            "Дайджест",
            _build_archive_case_digest(ticket),
            "",
            "Экспорт",
            "HTML отчёт — спокойный case file для review, handoff и аудита.",
            "CSV выгрузка — структурированный материал для сверки и импорта.",
        ]
    )
    return "\n".join(lines)


def _build_archive_ticket_heading(ticket: HistoricalTicketSummary) -> str:
    if ticket.category_title:
        return f"{ticket.public_number} · {ticket.category_title}"
    return ticket.public_number


def _build_archive_meta(ticket: HistoricalTicketSummary) -> str:
    parts = [format_status(ticket.status).capitalize()]
    parts.append(f"Создана {format_timestamp(ticket.created_at)}")
    if ticket.closed_at is not None:
        parts.append(f"Закрыта {format_timestamp(ticket.closed_at)}")
    return " • ".join(parts)


def _build_ticket_period(ticket: TicketDetailsSummary) -> str:
    parts = [f"Создана {format_timestamp(ticket.created_at)}"]
    if ticket.closed_at is not None:
        parts.append(f"Закрыта {format_timestamp(ticket.closed_at)}")
    return "\n".join(parts)


def _build_archive_case_digest(ticket: TicketDetailsSummary) -> str:
    messages_count = len(ticket.message_history)
    notes_count = len(ticket.internal_notes)
    attachments_count = sum(
        1 for message in ticket.message_history if message.attachment is not None
    )
    first_client_text = next(
        (
            message.text
            for message in ticket.message_history
            if message.sender_type.value == "client" and message.text
        ),
        None,
    )
    latest_text = ticket.last_message_text
    lines = [
        f"Сообщений · {messages_count}",
        f"Вложений · {attachments_count}",
        f"Заметок · {notes_count}",
    ]
    if first_client_text:
        lines.append(f"Старт · {shorten_text(' '.join(first_client_text.split()), 120)}")
    if latest_text:
        lines.append(f"Финал · {shorten_text(' '.join(latest_text.split()), 120)}")
    return "\n".join(lines)
