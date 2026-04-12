from __future__ import annotations

from datetime import UTC, datetime

from application.ai.summaries import TicketAssistSnapshot, TicketSummaryStatus
from application.use_cases.tickets.summaries import TicketDetailsSummary


def format_ticket_assist_snapshot(
    *,
    ticket: TicketDetailsSummary,
    snapshot: TicketAssistSnapshot,
) -> str:
    lines = [f"Подсказки по заявке {ticket.public_number}", "", ticket.subject]

    if not snapshot.available:
        lines.extend(
            [
                "",
                "AI-помощь сейчас недоступна.",
                snapshot.unavailable_reason
                or "Продолжайте работу через карточку и библиотеку макросов.",
            ]
        )
        return "\n".join(lines)

    lines.extend(["", _format_summary_status(snapshot)])
    if snapshot.summary_generated_at is not None:
        lines.append(f"Актуально на {_format_generated_at(snapshot.summary_generated_at)}")

    if snapshot.short_summary:
        lines.extend(["", "Краткая суть", snapshot.short_summary])
    if snapshot.user_goal:
        lines.extend(["", "Что хотел пользователь", snapshot.user_goal])
    if snapshot.actions_taken:
        lines.extend(["", "Что уже сделано", snapshot.actions_taken])
    if snapshot.current_status:
        lines.extend(["", "Текущее состояние", snapshot.current_status])

    lines.extend(["", "Рекомендуемые макросы"])
    if snapshot.macro_suggestions:
        for index, suggestion in enumerate(snapshot.macro_suggestions, start=1):
            lines.extend([f"{index}. {suggestion.title}", f"   Почему: {suggestion.reason}", ""])
    else:
        lines.append(
            "Сейчас нет достаточно точных подсказок. "
            "Обычная библиотека макросов остаётся под рукой."
        )

    if snapshot.status_note:
        lines.extend(["", snapshot.status_note])
    elif snapshot.unavailable_reason:
        lines.extend(["", snapshot.unavailable_reason])

    if snapshot.model_id:
        lines.extend(["", f"Модель: {snapshot.model_id}"])
    return "\n".join(lines)


def _format_summary_status(snapshot: TicketAssistSnapshot) -> str:
    if snapshot.summary_status is TicketSummaryStatus.FRESH:
        return "Сводка актуальна."
    if snapshot.summary_status is TicketSummaryStatus.STALE:
        return "Сводка требует обновления."
    return "Сводка ещё не подготовлена."


def _format_generated_at(value: datetime) -> str:
    normalized = value.astimezone(UTC)
    return normalized.strftime("%d.%m.%Y %H:%M UTC")
