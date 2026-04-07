from __future__ import annotations

from bot.texts.buttons import (
    CANCEL_BUTTON_TEXT,
    HELP_BUTTON_TEXT,
    OPERATORS_BUTTON_TEXT,
    QUEUE_BUTTON_TEXT,
    STATS_BUTTON_TEXT,
    TAKE_NEXT_BUTTON_TEXT,
)
from bot.texts.system import (
    format_diagnostics_report,
    get_command_hints,
    get_help_intro_lines,
    get_start_lines,
)
from domain.enums.roles import UserRole


def build_start_text(role: UserRole) -> str:
    return "\n".join(get_start_lines(role))


def build_help_text(role: UserRole) -> str:
    lines = [*get_help_intro_lines(role), "", "Команды"]
    lines.extend(
        f"{command_hint.command} - {command_hint.description}"
        for command_hint in get_command_hints(role)
    )

    navigation_lines = _build_navigation_help(role)
    if navigation_lines:
        lines.extend(["", "Кнопки меню", *navigation_lines])

    return "\n".join(lines)


__all__ = ["build_help_text", "build_start_text", "format_diagnostics_report"]


def _build_navigation_help(role: UserRole) -> list[str]:
    if role == UserRole.SUPER_ADMIN:
        return [
            f"«{QUEUE_BUTTON_TEXT}» - открыть очередь",
            f"«{TAKE_NEXT_BUTTON_TEXT}» - взять заявку",
            f"«{STATS_BUTTON_TEXT}» - посмотреть статистику",
            f"«{CANCEL_BUTTON_TEXT}» - отменить текущее действие",
            f"«{OPERATORS_BUTTON_TEXT}» - открыть список операторов",
            f"«{HELP_BUTTON_TEXT}» - открыть справку",
        ]
    if role == UserRole.OPERATOR:
        return [
            f"«{QUEUE_BUTTON_TEXT}» - открыть очередь",
            f"«{TAKE_NEXT_BUTTON_TEXT}» - взять заявку",
            f"«{STATS_BUTTON_TEXT}» - посмотреть статистику",
            f"«{CANCEL_BUTTON_TEXT}» - отменить текущее действие",
            f"«{HELP_BUTTON_TEXT}» - открыть справку",
        ]
    return [f"«{HELP_BUTTON_TEXT}» - открыть справку"]
