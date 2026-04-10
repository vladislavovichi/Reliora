from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from application.use_cases.tickets.summaries import (
    MacroSummary,
    OperatorSummary,
    TagSummary,
    TicketAttachmentSummary,
)
from bot.formatters.ticket_messages import build_message_preview
from domain.enums.tickets import TicketMessageSenderType, TicketStatus
from domain.tickets import format_status_for_humans


def format_tags(tags: Sequence[str]) -> str:
    if not tags:
        return "-"
    return ", ".join(tags)


def format_last_message(
    message_text: str | None,
    attachment: TicketAttachmentSummary | None,
    sender_type: TicketMessageSenderType | None,
) -> str:
    preview = build_message_preview(text=message_text, attachment=attachment)
    if not preview:
        return "Сообщений пока нет."

    preview = shorten_text(preview, 160)
    if sender_type is None:
        return preview

    sender = format_sender_type(sender_type).capitalize()
    return f"{sender} — {preview}"


def format_history_sender(
    sender_type: TicketMessageSenderType,
    *,
    sender_operator_name: str | None,
) -> str:
    if sender_type == TicketMessageSenderType.OPERATOR:
        if sender_operator_name:
            return f"Оператор {sender_operator_name}"
        return "Оператор"
    if sender_type == TicketMessageSenderType.CLIENT:
        return "Клиент"
    return "Система"


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


def format_tag_button_text(tag: TagSummary, *, selected: bool) -> str:
    prefix = "Снять" if selected else "Добавить"
    return f"{prefix} · {tag.name}"


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


def shorten_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."
