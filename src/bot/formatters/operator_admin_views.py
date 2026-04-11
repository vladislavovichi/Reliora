from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from urllib.parse import quote

from application.use_cases.tickets.summaries import OperatorSummary, TagSummary
from bot.formatters.operator_primitives import format_operator_line, format_tags


def format_operator_list_response(
    *,
    operators: Sequence[OperatorSummary],
    super_admin_telegram_user_ids: Sequence[int],
) -> str:
    super_admins = ", ".join(str(item) for item in super_admin_telegram_user_ids) or "-"
    lines = [
        "Операторы",
        f"В команде: {len(operators)}",
        "",
        "Суперадминистраторы",
        super_admins,
        "",
        "Команда",
    ]

    if not operators:
        lines.append("- пока пусто")
    else:
        for operator in operators:
            lines.append(f"- {format_operator_line(operator)}")

    lines.extend(["", "Откройте оператора ниже, пригласите нового или обновите список."])
    return "\n".join(lines)


def format_operator_detail_response(operator: OperatorSummary) -> str:
    lines = [
        "Оператор",
        "",
        "Имя",
        operator.display_name,
        "",
        "Telegram ID",
        str(operator.telegram_user_id),
    ]
    if operator.username:
        lines.extend(["", "Username", f"@{operator.username}"])
    lines.extend(["", "Профиль Telegram", build_operator_telegram_link(operator)])
    return "\n".join(lines)


def format_operator_invite_response(
    *,
    code: str,
    deep_link: str,
    expires_at: datetime,
) -> str:
    lines = [
        "Приглашение для оператора",
        "",
        "Код",
        code,
        "",
        "Ссылка",
        deep_link,
        "",
        "Условия",
        "Одно использование",
        f"Действует до {format_operator_invite_timestamp(expires_at)}",
    ]
    return "\n".join(lines)


def format_operator_onboarding_prompt(*, deep_link_code: str, expires_at: datetime) -> str:
    lines = [
        "Приглашение оператора подтверждено.",
        "",
        "Укажите имя, которое команда увидит в рабочих карточках.",
        "",
        "Код",
        deep_link_code,
        "",
        "Срок действия",
        format_operator_invite_timestamp(expires_at),
    ]
    return "\n".join(lines)


def format_operator_onboarding_confirmation(*, display_name: str) -> str:
    lines = [
        "Проверьте имя оператора",
        "",
        "Имя",
        display_name,
        "",
        "После подтверждения роль оператора будет активирована сразу.",
    ]
    return "\n".join(lines)


def build_operator_telegram_link(operator: OperatorSummary) -> str:
    if operator.username:
        return f"https://t.me/{quote(operator.username)}"
    return f"tg://user?id={operator.telegram_user_id}"


def format_operator_invite_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%d.%m.%Y %H:%M UTC")


def format_ticket_tags_response(
    public_number: str,
    ticket_tags: Sequence[str],
    available_tags: Sequence[TagSummary],
) -> str:
    lines = [
        f"Заявка {public_number}",
        "",
        "Метки",
        format_tags(ticket_tags),
        "",
        "Каталог",
        format_tags(tuple(tag.name for tag in available_tags)),
        "",
        "Нажмите на метку ниже.",
    ]
    return "\n".join(lines)
