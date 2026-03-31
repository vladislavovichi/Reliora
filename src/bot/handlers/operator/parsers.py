from __future__ import annotations

from uuid import UUID


def parse_ticket_public_id(value: str | None) -> UUID | None:
    if value is None:
        return None

    try:
        return UUID(value)
    except ValueError:
        return None


def parse_ticket_argument_with_text(args: str | None) -> tuple[UUID, str] | None:
    if args is None:
        return None

    parts = args.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None

    ticket_public_id = parse_ticket_public_id(parts[0])
    if ticket_public_id is None:
        return None

    tag_name = parts[1].strip()
    if not tag_name:
        return None

    return ticket_public_id, tag_name


def parse_reassign_target(text: str) -> tuple[int, str] | None:
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return None

    try:
        telegram_user_id = int(parts[0])
    except ValueError:
        return None

    display_name = parts[1].strip() if len(parts) > 1 else f"Оператор {telegram_user_id}"
    if not display_name:
        display_name = f"Оператор {telegram_user_id}"
    return telegram_user_id, display_name


def parse_telegram_user_id(value: str | None) -> int | None:
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    try:
        return int(stripped)
    except ValueError:
        return None


def parse_operator_argument_with_optional_name(args: str | None) -> tuple[int, str] | None:
    if args is None:
        return None

    parts = args.strip().split(maxsplit=1)
    if not parts:
        return None

    try:
        telegram_user_id = int(parts[0])
    except ValueError:
        return None

    display_name = parts[1].strip() if len(parts) > 1 else f"Оператор {telegram_user_id}"
    if not display_name:
        display_name = f"Оператор {telegram_user_id}"
    return telegram_user_id, display_name
