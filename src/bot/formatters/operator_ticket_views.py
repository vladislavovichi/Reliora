from __future__ import annotations

from collections.abc import Sequence

from application.use_cases.tickets.summaries import (
    OperatorTicketSummary,
    QueuedTicketSummary,
    TicketDetailsSummary,
    TicketInternalNoteSummary,
    TicketMessageSummary,
)
from bot.formatters.operator_primitives import (
    format_history_sender,
    format_last_message,
    format_priority,
    format_status,
    format_tags,
    format_timestamp,
    shorten_text,
)
from bot.formatters.ticket_messages import format_history_body
from domain.enums.tickets import TicketStatus

HISTORY_CHUNK_LIMIT = 3500
NOTES_CHUNK_LIMIT = 3500


def format_queue_page(
    tickets: Sequence[QueuedTicketSummary],
    *,
    current_page: int,
    total_pages: int,
) -> str:
    return _format_ticket_index_page(
        title="Очередь",
        tickets=tickets,
        current_page=current_page,
        total_pages=total_pages,
        footer=(
            "Откройте заявку, чтобы посмотреть историю и действия. "
            "Аналитика доступна из «Статистика»."
        ),
    )


def format_operator_ticket_page(
    tickets: Sequence[OperatorTicketSummary],
    *,
    current_page: int,
    total_pages: int,
) -> str:
    return _format_ticket_index_page(
        title="Мои заявки",
        tickets=tickets,
        current_page=current_page,
        total_pages=total_pages,
        footer="Откройте заявку, чтобы продолжить диалог. Экспорт находится в «Ещё».",
    )


def format_ticket_details(
    ticket: TicketDetailsSummary,
    *,
    is_active: bool = False,
) -> str:
    lines = [
        f"Заявка {ticket.public_number}",
        _format_ticket_heading(ticket),
    ]
    if is_active:
        lines.extend(["", "Текущий диалог"])

    lines.extend(["", "Тема", ticket.subject])
    _append_section(lines, "Категория", ticket.category_title)
    _append_section(lines, "Оператор", _format_assigned_operator(ticket))
    _append_section(lines, "Создана", format_timestamp(ticket.created_at))
    if ticket.tags:
        _append_section(lines, "Теги", format_tags(ticket.tags))
    _append_section(
        lines,
        "Последнее сообщение",
        format_last_message(
            ticket.last_message_text,
            ticket.last_message_attachment,
            ticket.last_message_sender_type,
        ),
    )
    return "\n".join(lines)


def format_active_ticket_context(ticket: TicketDetailsSummary) -> str:
    lines = [
        "Текущий диалог",
        _format_ticket_context_line(ticket),
        shorten_text(ticket.subject, 96),
    ]
    meta_lines = _build_ticket_context_meta(ticket)
    if meta_lines:
        lines.append("")
        lines.extend(meta_lines)
    return "\n".join(lines)


def format_ticket_more_actions(
    ticket: TicketDetailsSummary,
    *,
    is_active: bool = False,
) -> str:
    lines = [format_active_ticket_context(ticket) if is_active else format_ticket_details(ticket)]
    lines.extend(["", "Ещё"])

    change_actions = ["Метки"]
    if ticket.status in {TicketStatus.ASSIGNED, TicketStatus.ESCALATED}:
        change_actions.append("Передать")
    lines.extend(["", "Изменить", " · ".join(change_actions)])

    lines.extend(["", "Внутреннее", "Заметки"])

    lines.extend(["", "Отчёт", "Экспорт · CSV · HTML"])

    status_actions = ["Карточка"]
    if ticket.status in {TicketStatus.QUEUED, TicketStatus.ASSIGNED}:
        status_actions.insert(0, "Эскалация")
    lines.extend(["", "Статус и детали", " · ".join(status_actions)])
    return "\n".join(lines)


def format_ticket_export_actions(
    ticket: TicketDetailsSummary,
    *,
    is_active: bool = False,
) -> str:
    lines = [format_active_ticket_context(ticket) if is_active else format_ticket_details(ticket)]
    lines.extend(
        [
            "",
            "Экспорт",
            "",
            "Форматы",
            "CSV · HTML",
            "",
            "Отчёт включает карточку заявки, таймстемпы, полную переписку и заметки.",
        ]
    )
    return "\n".join(lines)


def format_ticket_notes_text(ticket: TicketDetailsSummary) -> str:
    lines = [format_active_ticket_context(ticket), "", "Заметки"]
    if not ticket.internal_notes:
        lines.extend(["", "Внутренних заметок пока нет."])
        return "\n".join(lines)

    latest_note = ticket.internal_notes[-1]
    lines.extend(
        [
            "",
            f"Всего: {len(ticket.internal_notes)}",
            f"Последняя · {_format_note_author(latest_note)}",
            format_timestamp(latest_note.created_at),
        ]
    )
    return "\n".join(lines)


def format_ticket_history_chunks(ticket: TicketDetailsSummary) -> tuple[str, ...]:
    if not ticket.message_history:
        return ("Переписка\n\nСообщений пока нет.",)

    chunks: list[str] = []
    current_chunk = "Переписка"
    continuation_header = "Переписка, продолжение"

    for index, message in enumerate(ticket.message_history, start=1):
        for entry in _format_ticket_history_entry_parts(index=index, message=message):
            separator = "\n\n" if current_chunk else ""
            candidate = f"{current_chunk}{separator}{entry}" if current_chunk else entry
            if len(candidate) <= HISTORY_CHUNK_LIMIT:
                current_chunk = candidate
                continue

            chunks.append(current_chunk)
            current_chunk = f"{continuation_header}\n\n{entry}"

    chunks.append(current_chunk)
    return tuple(chunks)


def _format_ticket_history_entry_parts(
    *,
    index: int,
    message: TicketMessageSummary,
) -> tuple[str, ...]:
    del index
    sender = format_history_sender(
        message.sender_type,
        sender_operator_name=message.sender_operator_name,
    )
    timestamp = format_timestamp(message.created_at)
    prefix = f"{sender} · {timestamp}\n"
    continuation_prefix = f"{sender} · {timestamp} · продолжение\n"
    text_limit = max(500, HISTORY_CHUNK_LIMIT - len(prefix) - 32)

    parts = _split_message_text(format_history_body(message), text_limit)
    if len(parts) == 1:
        return (f"{prefix}{parts[0]}",)

    result: list[str] = []
    for part_index, part in enumerate(parts):
        active_prefix = prefix if part_index == 0 else continuation_prefix
        result.append(f"{active_prefix}{part}")
    return tuple(result)


def _split_message_text(text: str, limit: int) -> tuple[str, ...]:
    normalized = text.rstrip()
    if len(normalized) <= limit:
        return (normalized,)

    parts: list[str] = []
    remaining = normalized
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at <= 0:
            split_at = limit

        parts.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    if remaining:
        parts.append(remaining)
    return tuple(parts)


def format_ticket_notes_chunks(ticket: TicketDetailsSummary) -> tuple[str, ...]:
    if not ticket.internal_notes:
        return ("Заметки\n\nВнутренних заметок пока нет.",)

    chunks: list[str] = []
    current_chunk = "Заметки"
    continuation_header = "Заметки, продолжение"

    for note in ticket.internal_notes:
        entry = _format_ticket_note_entry(note)
        separator = "\n\n" if current_chunk else ""
        candidate = f"{current_chunk}{separator}{entry}" if current_chunk else entry
        if len(candidate) <= NOTES_CHUNK_LIMIT:
            current_chunk = candidate
            continue

        chunks.append(current_chunk)
        current_chunk = f"{continuation_header}\n\n{entry}"

    chunks.append(current_chunk)
    return tuple(chunks)


def _format_ticket_heading(ticket: TicketDetailsSummary) -> str:
    return (
        f"{format_status(ticket.status).capitalize()} • "
        f"{format_priority(ticket.priority)} приоритет"
    )


def _format_ticket_context_line(ticket: TicketDetailsSummary) -> str:
    return f"{ticket.public_number} · {_format_ticket_heading(ticket)}"


def _format_assigned_operator(ticket: TicketDetailsSummary) -> str:
    if ticket.assigned_operator_id is None:
        return "не назначен"
    if ticket.assigned_operator_name:
        return ticket.assigned_operator_name
    return f"оператор #{ticket.assigned_operator_id}"


def _append_section(lines: list[str], title: str, value: str | None) -> None:
    if not value:
        return
    lines.extend(["", title, value])


def _build_ticket_context_meta(ticket: TicketDetailsSummary) -> tuple[str, ...]:
    items: list[str] = [f"Оператор · {_format_assigned_operator(ticket)}"]
    if ticket.tags:
        items.append(f"Теги · {format_tags(ticket.tags)}")
    if ticket.category_title:
        items.insert(0, f"Категория · {ticket.category_title}")
    return tuple(items)


def _format_ticket_index_page(
    *,
    title: str,
    tickets: Sequence[QueuedTicketSummary | OperatorTicketSummary],
    current_page: int,
    total_pages: int,
    footer: str,
) -> str:
    lines = [title, f"Страница {current_page} / {total_pages}", ""]

    for index, ticket in enumerate(tickets, start=1):
        lines.extend(
            [
                f"{index}. {ticket.public_number}",
                f"   {_format_ticket_list_meta(ticket.priority, ticket.status)}",
                f"   {shorten_text(ticket.subject, 72)}",
                "",
            ]
        )

    lines.append(footer)
    return "\n".join(lines)


def _format_ticket_list_meta(priority: str, status: TicketStatus) -> str:
    return f"{format_status(status).capitalize()} • {format_priority(priority)} приоритет"


def _format_ticket_note_entry(note: TicketInternalNoteSummary) -> str:
    return (
        f"{_format_note_author(note)} · {format_timestamp(note.created_at)}\n{note.text.rstrip()}"
    )


def _format_note_author(note: TicketInternalNoteSummary) -> str:
    if note.author_operator_name:
        return note.author_operator_name
    return f"оператор #{note.author_operator_id}"
