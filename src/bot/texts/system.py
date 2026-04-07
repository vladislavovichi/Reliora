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
    CommandHint("/stats", "показать статистику"),
    CommandHint("/health", "проверить состояние сервиса"),
    CommandHint("/ticket <ticket_public_id>", "открыть карточку заявки"),
    CommandHint("/macros [ticket_public_id]", "показать макросы"),
    CommandHint("/tags <ticket_public_id>", "показать теги заявки"),
    CommandHint("/alltags", "показать все теги"),
    CommandHint("/addtag <ticket_public_id> <tag>", "добавить тег к заявке"),
    CommandHint("/rmtag <ticket_public_id> <tag>", "снять тег с заявки"),
    CommandHint("/cancel", "отменить текущее действие"),
)
SUPER_ADMIN_COMMAND_HINTS = (
    CommandHint("/add_operator <telegram_user_id> [display_name]", "добавить оператора"),
    CommandHint("/remove_operator <telegram_user_id>", "снять права оператора"),
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
            "Вы вошли как суперадминистратор.",
            "Здесь доступны рабочие действия оператора и управление командой.",
            "Меню ниже отвечает за навигацию, кнопки под заявкой — за действия по ней.",
        ]
    if role == UserRole.OPERATOR:
        return [
            "Вы вошли как оператор.",
            "Очередь, статистика и быстрые действия доступны в меню ниже.",
            "Для работы с конкретной заявкой используйте кнопки под её карточкой.",
        ]
    return [
        "Это бот поддержки.",
        "Просто отправьте сообщение в чат — бот создаст заявку или добавит его в текущую.",
        "Если понадобится подсказка, откройте справку кнопкой ниже или командой /help.",
    ]


def get_help_intro_lines(role: UserRole) -> list[str]:
    if role == UserRole.SUPER_ADMIN:
        return [
            "Справка для суперадминистратора.",
            (
                "Основные действия собраны в меню, "
                "а работа с заявками доступна через кнопки под карточкой."
            ),
        ]
    if role == UserRole.OPERATOR:
        return [
            "Справка для оператора.",
            (
                "Очередь и быстрые действия находятся в меню, "
                "работа с заявкой — в кнопках под карточкой."
            ),
        ]
    return [
        "Справка.",
        "Чтобы создать заявку или продолжить текущую, просто отправьте сообщение в этот чат.",
    ]


def get_command_hints(role: UserRole) -> tuple[CommandHint, ...]:
    command_hints = [*COMMON_COMMAND_HINTS]
    if role in {UserRole.OPERATOR, UserRole.SUPER_ADMIN}:
        command_hints.extend(OPERATOR_COMMAND_HINTS)
    if role == UserRole.SUPER_ADMIN:
        command_hints.extend(SUPER_ADMIN_COMMAND_HINTS)
    return tuple(command_hints)
