from __future__ import annotations

from dataclasses import dataclass

from application.services.diagnostics import DiagnosticsReport
from domain.enums.roles import UserRole

PING_RESPONSE_TEXT = "понг"


@dataclass(slots=True, frozen=True)
class CommandHint:
    command: str
    description: str


COMMON_COMMAND_HINTS = (
    CommandHint("/start", "открыть главное меню"),
    CommandHint("/help", "показать краткую справку"),
)
OPERATOR_COMMAND_HINTS = (
    CommandHint("/stats", "открыть статистику"),
    CommandHint("/health", "проверить состояние сервиса"),
    CommandHint("/ticket <ticket_public_id>", "открыть карточку заявки"),
    CommandHint("/macros [ticket_public_id]", "открыть макросы"),
    CommandHint("/tags <ticket_public_id>", "открыть теги заявки"),
    CommandHint("/alltags", "показать доступные теги"),
    CommandHint("/addtag <ticket_public_id> <tag>", "добавить тег к заявке"),
    CommandHint("/rmtag <ticket_public_id> <tag>", "снять тег с заявки"),
    CommandHint("/cancel", "отменить текущее действие"),
)
SUPER_ADMIN_COMMAND_HINTS = (
    CommandHint("/add_operator <telegram_user_id> [display_name]", "добавить оператора в команду"),
    CommandHint("/remove_operator <telegram_user_id>", "снять роль оператора"),
)


def format_diagnostics_report(report: DiagnosticsReport) -> str:
    status_line = "Сервис работает стабильно." if report.is_healthy else "Есть проблемы с сервисом."
    lines = [status_line, ""]
    lines.extend(
        f"- {check.name}: {'в порядке' if check.ok else 'ошибка'} ({check.detail})"
        for check in report.checks
    )
    return "\n".join(lines)


def get_start_lines(role: UserRole) -> list[str]:
    if role == UserRole.SUPER_ADMIN:
        return [
            "Рабочее меню суперадминистратора.",
            "Здесь доступны инструменты оператора и управление командой.",
            "Откройте заявку, чтобы увидеть её детали и действия.",
        ]
    if role == UserRole.OPERATOR:
        return [
            "Рабочее меню оператора.",
            "Очередь, статистика и быстрые действия доступны ниже.",
            "Откройте заявку, чтобы увидеть детали и продолжить работу.",
        ]
    return [
        "Поддержка в Telegram.",
        "Напишите сообщение, и бот создаст заявку или добавит его в текущую.",
        "Если понадобится подсказка, откройте справку кнопкой ниже.",
    ]


def get_help_intro_lines(role: UserRole) -> list[str]:
    if role == UserRole.SUPER_ADMIN:
        return [
            "Справка суперадминистратора.",
            "Основные разделы доступны в меню, действия по заявкам — в карточке.",
        ]
    if role == UserRole.OPERATOR:
        return [
            "Справка оператора.",
            "Основные разделы доступны в меню, действия по заявкам — в карточке.",
        ]
    return [
        "Справка.",
        "Чтобы создать заявку или продолжить текущую, просто напишите в этот чат.",
    ]


def get_command_hints(role: UserRole) -> tuple[CommandHint, ...]:
    command_hints = [*COMMON_COMMAND_HINTS]
    if role in {UserRole.OPERATOR, UserRole.SUPER_ADMIN}:
        command_hints.extend(OPERATOR_COMMAND_HINTS)
    if role == UserRole.SUPER_ADMIN:
        command_hints.extend(SUPER_ADMIN_COMMAND_HINTS)
    return tuple(command_hints)
