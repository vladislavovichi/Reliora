from __future__ import annotations

from collections.abc import Sequence

from application.use_cases.tickets.summaries import TicketCategorySummary

CATEGORY_PAGE_SIZE = 8


def paginate_categories(
    categories: Sequence[TicketCategorySummary],
    *,
    page: int,
) -> tuple[tuple[TicketCategorySummary, ...], int, int]:
    total_pages = max(1, (len(categories) + CATEGORY_PAGE_SIZE - 1) // CATEGORY_PAGE_SIZE)
    safe_page = min(max(page, 1), total_pages)
    start = (safe_page - 1) * CATEGORY_PAGE_SIZE
    end = start + CATEGORY_PAGE_SIZE
    return tuple(categories[start:end]), safe_page, total_pages


def format_admin_category_list(
    categories: Sequence[TicketCategorySummary],
    *,
    current_page: int,
    total_pages: int,
) -> str:
    lines = ["Темы обращений", f"Страница {current_page} / {total_pages}", ""]
    if not categories:
        lines.append("Темы пока не настроены.")
    else:
        for index, category in enumerate(categories, start=1):
            lines.extend(
                [
                    f"{index}. {category.title}",
                    f"   {category.code} • {_format_category_status(category.is_active)}",
                    "",
                ]
            )
    lines.append("Откройте тему, чтобы изменить название или доступность.")
    return "\n".join(lines)


def format_admin_category_details(category: TicketCategorySummary) -> str:
    return "\n".join(
        [
            "Тема обращения",
            "",
            "Название",
            category.title,
            "",
            "Код",
            category.code,
            "",
            "Статус",
            _format_category_status(category.is_active),
        ]
    )


def _format_category_status(is_active: bool) -> str:
    return "доступна" if is_active else "скрыта"
