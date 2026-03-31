from __future__ import annotations

from collections.abc import Iterable


def parse_positive_int_list(value: object) -> tuple[int, ...]:
    items = _normalize_items(value)
    parsed_items: list[int] = []
    seen: set[int] = set()

    for item in items:
        if item == "":
            continue

        try:
            parsed_value = int(str(item).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("Значение должно содержать только положительные целые числа.") from exc

        if parsed_value <= 0:
            raise ValueError("Идентификаторы должны быть положительными целыми числами.")

        if parsed_value not in seen:
            seen.add(parsed_value)
            parsed_items.append(parsed_value)

    if not parsed_items:
        raise ValueError("Нужно указать хотя бы один Telegram ID супер администратора.")

    return tuple(parsed_items)


def _normalize_items(value: object) -> list[object]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",")]

    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return [item for item in value]

    return [value]
