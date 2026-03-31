from __future__ import annotations

from collections.abc import Sequence

from application.services.stats import HelpdeskOperationalStats
from application.use_cases.tickets import (
    MacroSummary,
    OperatorSummary,
    QueuedTicketSummary,
    TicketDetailsSummary,
)
from domain.enums.tickets import TicketMessageSenderType, TicketStatus
from domain.tickets import format_status_for_humans


def format_queued_ticket(ticket: QueuedTicketSummary) -> str:
    return "\n".join(
        [
            f"{ticket.public_number}",
            f"Публичный идентификатор: {ticket.public_id}",
            f"Статус: {format_status(ticket.status)}",
            f"Приоритет: {format_priority(ticket.priority)}",
            f"Тема: {ticket.subject}",
        ]
    )


def format_ticket_details(ticket: TicketDetailsSummary) -> str:
    assigned_operator = "не назначен"
    if ticket.assigned_operator_id is not None:
        assigned_name = ticket.assigned_operator_name or "оператор"
        assigned_operator = f"{assigned_name} (id={ticket.assigned_operator_id})"

    lines = [
        f"{ticket.public_number}",
        f"Публичный идентификатор: {ticket.public_id}",
        f"Статус: {format_status(ticket.status)}",
        f"Приоритет: {format_priority(ticket.priority)}",
        f"Тема: {ticket.subject}",
        f"Назначен: {assigned_operator}",
        f"Теги: {format_tags(ticket.tags)}",
        "Последнее сообщение: "
        f"{format_last_message(ticket.last_message_text, ticket.last_message_sender_type)}",
    ]
    return "\n".join(lines)


def format_macro_list(
    macros: Sequence[MacroSummary],
    ticket_details: TicketDetailsSummary | None,
) -> str:
    lines: list[str] = []
    if ticket_details is None:
        lines.append("Доступные макросы:")
    else:
        lines.append(f"Макросы для заявки {ticket_details.public_number}:")

    for macro in macros:
        lines.append(f"{macro.id}. {macro.title} — {format_macro_preview(macro.body)}")

    if ticket_details is None:
        lines.append("Используйте /macros <ticket_public_id>, чтобы применить макрос кнопкой.")
    else:
        lines.append("Выберите макрос кнопкой ниже.")
    return "\n".join(lines)


def format_operator_list_response(
    *,
    operators: Sequence[OperatorSummary],
    super_admin_telegram_user_ids: Sequence[int],
) -> str:
    lines = [
        "Управление операторами:",
        "Супер администраторы: " + ", ".join(str(item) for item in super_admin_telegram_user_ids),
        "",
        "Активные операторы:",
    ]

    if not operators:
        lines.append("- список операторов пуст")
    else:
        for operator in operators:
            lines.append(f"- {format_operator_line(operator)}")

    lines.extend(
        [
            "",
            "Команды:",
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
        f"Теги заявки {public_number}: {format_tags(ticket_tags)}",
        f"Доступные теги: {format_tags(available_tags)}",
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
        return "-"

    preview = " ".join(message_text.split())
    if len(preview) > 120:
        preview = f"{preview[:117]}..."

    if sender_type is None:
        return preview

    return f"[{format_sender_type(sender_type)}] {preview}"


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
    if len(label) > 24:
        label = f"{label[:21]}..."
    return f"{label} ({operator.telegram_user_id})"


def format_operator_line(operator: OperatorSummary) -> str:
    username = f" @{operator.username}" if operator.username else ""
    return f"{operator.display_name} (Telegram ID: {operator.telegram_user_id}){username}"


def format_operational_stats(stats: HelpdeskOperationalStats) -> str:
    lines = [
        "Операционная статистика:",
        f"Открытые заявки: {stats.total_open_tickets}",
        f"В очереди: {stats.queued_tickets_count}",
        f"Назначенные: {stats.assigned_tickets_count}",
        f"Эскалированные: {stats.escalated_tickets_count}",
        f"Закрытые: {stats.closed_tickets_count}",
        "",
        "Нагрузка по операторам:",
    ]

    if not stats.tickets_per_operator:
        lines.append("- нет активных назначений")
    else:
        for item in stats.tickets_per_operator:
            lines.append(f"- {item.display_name} (id={item.operator_id}): {item.ticket_count}")

    lines.extend(
        [
            "",
            "Средние времена:",
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
