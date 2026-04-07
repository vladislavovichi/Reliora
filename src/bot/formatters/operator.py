from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from application.services.stats import HelpdeskOperationalStats
from application.use_cases.tickets.summaries import (
    MacroSummary,
    OperatorSummary,
    QueuedTicketSummary,
    TicketDetailsSummary,
    TicketMessageSummary,
)
from domain.enums.tickets import TicketMessageSenderType, TicketStatus
from domain.tickets import format_status_for_humans

QUEUE_PAGE_SIZE = 5
HISTORY_CHUNK_LIMIT = 3500


def format_queued_ticket(ticket: QueuedTicketSummary) -> str:
    return "\n".join(
        [
            ticket.public_number,
            _format_queue_meta(ticket),
            _shorten_text(ticket.subject, 72),
        ]
    )


def format_queue_page(
    tickets: Sequence[QueuedTicketSummary],
    *,
    current_page: int,
    total_pages: int,
) -> str:
    lines = ["Очередь", f"Страница {current_page} / {total_pages}", ""]

    for index, ticket in enumerate(tickets, start=1):
        lines.extend(
            [
                f"{index}. {ticket.public_number}",
                f"   {_format_queue_meta(ticket)}",
                f"   {_shorten_text(ticket.subject, 72)}",
                "",
            ]
        )

    lines.append("Нажмите на заявку, чтобы открыть карточку.")
    return "\n".join(lines)


def format_ticket_details(ticket: TicketDetailsSummary) -> str:
    lines = [
        f"Заявка {ticket.public_number}",
        _format_ticket_heading(ticket),
        "",
        "Тема",
        ticket.subject,
    ]

    _append_section(lines, "Оператор", _format_assigned_operator(ticket))
    _append_section(lines, "Создана", format_timestamp(ticket.created_at))
    if ticket.tags:
        _append_section(lines, "Теги", format_tags(ticket.tags))
    _append_section(
        lines,
        "Последнее сообщение",
        format_last_message(ticket.last_message_text, ticket.last_message_sender_type),
    )
    return "\n".join(lines)


def format_ticket_history_chunks(ticket: TicketDetailsSummary) -> tuple[str, ...]:
    if not ticket.message_history:
        return ("Переписка\n\nСообщений пока нет.",)

    chunks: list[str] = []
    current_chunk = "Переписка"
    continuation_header = "Переписка, продолжение"

    for index, message in enumerate(ticket.message_history, start=1):
        for entry in format_ticket_history_entry_parts(index=index, message=message):
            separator = "\n\n" if current_chunk else ""
            candidate = f"{current_chunk}{separator}{entry}" if current_chunk else entry

            if len(candidate) <= HISTORY_CHUNK_LIMIT:
                current_chunk = candidate
                continue

            chunks.append(current_chunk)
            current_chunk = f"{continuation_header}\n\n{entry}"

    chunks.append(current_chunk)
    return tuple(chunks)


def format_ticket_history_entry(*, index: int, message: TicketMessageSummary) -> str:
    del index
    return (
        f"{format_history_sender(message)} · {format_timestamp(message.created_at)}\n"
        f"{message.text}"
    )


def format_ticket_history_entry_parts(
    *,
    index: int,
    message: TicketMessageSummary,
) -> tuple[str, ...]:
    sender = format_history_sender(message)
    timestamp = format_timestamp(message.created_at)
    prefix = f"{sender} · {timestamp}\n"
    continuation_prefix = f"{sender} · {timestamp} · продолжение\n"
    text_limit = max(500, HISTORY_CHUNK_LIMIT - len(prefix) - 32)

    parts = _split_message_text(message.text, text_limit)
    if len(parts) == 1:
        return (f"{prefix}{parts[0]}",)

    result: list[str] = []
    for part_index, part in enumerate(parts):
        active_prefix = prefix if part_index == 0 else continuation_prefix
        result.append(f"{active_prefix}{part}")
    return tuple(result)


def format_macro_list(
    macros: Sequence[MacroSummary],
    ticket_details: TicketDetailsSummary | None,
) -> str:
    lines: list[str] = []
    if ticket_details is None:
        lines.append("Макросы")
    else:
        lines.append(f"Макросы для заявки {ticket_details.public_number}")

    for macro in macros:
        lines.append(f"{macro.id}. {macro.title} — {format_macro_preview(macro.body)}")

    if ticket_details is None:
        lines.append("Откройте заявку, чтобы использовать макрос.")
    else:
        lines.append("Выберите макрос.")
    return "\n".join(lines)


def format_operator_list_response(
    *,
    operators: Sequence[OperatorSummary],
    super_admin_telegram_user_ids: Sequence[int],
) -> str:
    super_admins = ", ".join(str(item) for item in super_admin_telegram_user_ids) or "-"
    lines = ["Команда", "", "Суперадминистраторы", super_admins, "", "Операторы"]

    if not operators:
        lines.append("- пока пусто")
    else:
        for operator in operators:
            lines.append(f"- {format_operator_line(operator)}")

    lines.extend(
        [
            "",
            "Команды",
            "/add_operator <telegram_user_id> [display_name]",
            "/remove_operator <telegram_user_id>",
        ]
    )
    return "\n".join(lines)


def format_ticket_tags_response(
    public_number: str,
    ticket_tags: Sequence[str],
    available_tags: Sequence[str],
) -> str:
    lines = [
        f"Заявка {public_number}",
        f"Теги: {format_tags(ticket_tags)}",
        f"Доступные: {format_tags(available_tags)}",
        "Добавить: /addtag <ticket_public_id> <tag>",
        "Снять: /rmtag <ticket_public_id> <tag>",
    ]
    return "\n".join(lines)


def format_tags(tags: Sequence[str]) -> str:
    if not tags:
        return "-"
    return ", ".join(tags)


def format_last_message(
    message_text: str | None,
    sender_type: TicketMessageSenderType | None,
) -> str:
    if not message_text:
        return "Сообщений пока нет."

    preview = _shorten_text(" ".join(message_text.split()), 160)

    if sender_type is None:
        return preview

    sender = format_sender_type(sender_type).capitalize()
    return f"{sender} — {preview}"


def format_history_sender(message: TicketMessageSummary) -> str:
    if message.sender_type == TicketMessageSenderType.OPERATOR:
        if message.sender_operator_name:
            return f"Оператор {message.sender_operator_name}"
        return "Оператор"
    if message.sender_type == TicketMessageSenderType.CLIENT:
        return "Клиент"
    return "Система"


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


def format_macro_preview(text: str) -> str:
    preview = " ".join(text.split())
    if len(preview) > 80:
        return f"{preview[:77]}..."
    return preview


def format_macro_button_text(macro: MacroSummary) -> str:
    label = macro.title.strip() or f"Макрос {macro.id}"
    if len(label) > 32:
        return f"{label[:29]}..."
    return label


def format_operator_button_text(operator: OperatorSummary) -> str:
    label = operator.display_name.strip() or str(operator.telegram_user_id)
    if len(label) > 20:
        label = f"{label[:17]}..."
    return f"{label} · {operator.telegram_user_id}"


def format_operator_line(operator: OperatorSummary) -> str:
    parts = [operator.display_name, str(operator.telegram_user_id)]
    if operator.username:
        parts.append(f"@{operator.username}")
    return " · ".join(parts)


def format_operational_stats(stats: HelpdeskOperationalStats) -> str:
    lines = [
        "Статистика",
        f"Открытые заявки: {stats.total_open_tickets}",
        f"В очереди: {stats.queued_tickets_count}",
        f"Назначенные: {stats.assigned_tickets_count}",
        f"Эскалированные: {stats.escalated_tickets_count}",
        f"Закрытые: {stats.closed_tickets_count}",
        "",
        "Нагрузка по операторам",
    ]

    if not stats.tickets_per_operator:
        lines.append("- активных назначений нет")
    else:
        for item in stats.tickets_per_operator:
            lines.append(f"- {item.display_name} (id={item.operator_id}): {item.ticket_count}")

    lines.extend(
        [
            "",
            "Среднее время",
            f"Первый ответ: {format_duration(stats.average_first_response_time_seconds)}",
            f"Решение: {format_duration(stats.average_resolution_time_seconds)}",
        ]
    )
    return "\n".join(lines)


def format_status(status: TicketStatus) -> str:
    return format_status_for_humans(status)


def format_priority(priority: str) -> str:
    priority_labels = {
        "low": "низкий",
        "normal": "обычный",
        "high": "высокий",
        "urgent": "срочный",
    }
    return priority_labels.get(priority, priority)


def format_sender_type(sender_type: TicketMessageSenderType) -> str:
    sender_labels = {
        TicketMessageSenderType.CLIENT: "клиент",
        TicketMessageSenderType.OPERATOR: "оператор",
        TicketMessageSenderType.SYSTEM: "система",
    }
    return sender_labels.get(sender_type, sender_type.value)


def format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%d.%m.%Y %H:%M UTC")


def _format_queue_meta(ticket: QueuedTicketSummary) -> str:
    return f"{format_priority(ticket.priority).capitalize()} приоритет"


def _format_ticket_heading(ticket: TicketDetailsSummary) -> str:
    return (
        f"{format_status(ticket.status).capitalize()} • "
        f"{format_priority(ticket.priority)} приоритет"
    )


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


def _shorten_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "нет данных"
    if seconds < 60:
        return f"{seconds} сек"

    minutes, remaining_seconds = divmod(seconds, 60)
    hours, remaining_minutes = divmod(minutes, 60)
    days, remaining_hours = divmod(hours, 24)

    parts: list[str] = []
    if days > 0:
        parts.append(f"{days} д")
    if remaining_hours > 0:
        parts.append(f"{remaining_hours} ч")
    if remaining_minutes > 0:
        parts.append(f"{remaining_minutes} мин")
    if not parts:
        parts.append(f"{remaining_seconds} сек")
    return " ".join(parts[:2])
