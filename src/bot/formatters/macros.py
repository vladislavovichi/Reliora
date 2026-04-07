from __future__ import annotations

from collections.abc import Sequence

from application.use_cases.tickets.summaries import MacroSummary

MACRO_PAGE_SIZE = 6


def paginate_macros(
    macros: Sequence[MacroSummary],
    *,
    page: int,
) -> tuple[tuple[MacroSummary, ...], int, int]:
    total_pages = max(1, (len(macros) + MACRO_PAGE_SIZE - 1) // MACRO_PAGE_SIZE)
    safe_page = min(max(page, 1), total_pages)
    start = (safe_page - 1) * MACRO_PAGE_SIZE
    end = start + MACRO_PAGE_SIZE
    return tuple(macros[start:end]), safe_page, total_pages


def format_macro_library(macros: Sequence[MacroSummary]) -> str:
    lines = ["Макросы", ""]
    for index, macro in enumerate(macros, start=1):
        lines.extend([f"{index}. {macro.title}", f"   {format_macro_preview(macro.body)}", ""])
    lines.append("Макросы доступны из карточки заявки.")
    return "\n".join(lines)


def format_operator_macro_picker(
    *,
    ticket_public_number: str,
    macros: Sequence[MacroSummary],
    current_page: int,
    total_pages: int,
) -> str:
    lines = [
        f"Макросы для заявки {ticket_public_number}",
        f"Страница {current_page} / {total_pages}",
        "",
    ]

    for index, macro in enumerate(macros, start=1):
        lines.extend([f"{index}. {macro.title}", f"   {format_macro_preview(macro.body)}", ""])

    lines.append("Выберите макрос.")
    return "\n".join(lines)


def format_operator_macro_preview(
    *,
    ticket_public_number: str,
    macro: MacroSummary,
) -> str:
    return "\n".join(
        [
            f"Заявка {ticket_public_number}",
            "",
            "Макрос",
            macro.title,
            "",
            "Текст",
            macro.body,
        ]
    )


def format_admin_macro_list(
    macros: Sequence[MacroSummary],
    *,
    current_page: int,
    total_pages: int,
) -> str:
    lines = ["Макросы", f"Страница {current_page} / {total_pages}", ""]

    if not macros:
        lines.append("Макросов пока нет.")
    else:
        for index, macro in enumerate(macros, start=1):
            lines.extend([f"{index}. {macro.title}", f"   {format_macro_preview(macro.body)}", ""])

    lines.append("Выберите макрос или создайте новый.")
    return "\n".join(lines)


def format_admin_macro_details(macro: MacroSummary) -> str:
    return "\n".join(["Макрос", "", "Название", macro.title, "", "Текст", macro.body])


def format_admin_macro_create_preview(*, title: str, body: str) -> str:
    return "\n".join(["Новый макрос", "", "Название", title, "", "Текст", body])


def format_macro_preview(text: str) -> str:
    preview = " ".join(text.split())
    if len(preview) > 80:
        return f"{preview[:77]}..."
    return preview
