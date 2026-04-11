from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Final

from application.use_cases.tickets.summaries import HistoricalTicketSummary

ALL_ARCHIVE_CATEGORIES_ID: Final[int] = 0
UNCATEGORIZED_ARCHIVE_CATEGORY_ID: Final[int] = -1


@dataclass(slots=True, frozen=True)
class ArchiveCategoryFilter:
    id: int
    title: str
    ticket_count: int


@dataclass(slots=True, frozen=True)
class ArchiveBrowserPage:
    tickets: tuple[HistoricalTicketSummary, ...]
    filters: tuple[ArchiveCategoryFilter, ...]
    current_page: int
    total_pages: int
    selected_category_id: int
    selected_category_title: str | None
    total_filtered_tickets: int


def build_archive_browser_page(
    *,
    tickets: tuple[HistoricalTicketSummary, ...] | list[HistoricalTicketSummary],
    page: int,
    category_id: int = ALL_ARCHIVE_CATEGORIES_ID,
    page_size: int = 6,
) -> ArchiveBrowserPage:
    all_tickets = tuple(tickets)
    filters = build_archive_category_filters(all_tickets)
    filtered_tickets = tuple(filter_archived_tickets(tickets=all_tickets, category_id=category_id))
    total_pages = max(1, ceil(len(filtered_tickets) / page_size)) if page_size > 0 else 1
    safe_page = min(max(page, 1), total_pages)
    start = (safe_page - 1) * page_size
    end = start + page_size
    return ArchiveBrowserPage(
        tickets=filtered_tickets[start:end],
        filters=filters,
        current_page=safe_page,
        total_pages=total_pages,
        selected_category_id=category_id,
        selected_category_title=resolve_archive_category_title(
            filters=filters,
            category_id=category_id,
        ),
        total_filtered_tickets=len(filtered_tickets),
    )


def build_archive_category_filters(
    tickets: tuple[HistoricalTicketSummary, ...] | list[HistoricalTicketSummary],
) -> tuple[ArchiveCategoryFilter, ...]:
    counts: dict[int, int] = {ALL_ARCHIVE_CATEGORIES_ID: len(tickets)}
    titles: dict[int, str] = {}

    for ticket in tickets:
        if ticket.category_id is None:
            counts[UNCATEGORIZED_ARCHIVE_CATEGORY_ID] = (
                counts.get(UNCATEGORIZED_ARCHIVE_CATEGORY_ID, 0) + 1
            )
            titles.setdefault(UNCATEGORIZED_ARCHIVE_CATEGORY_ID, "Без темы")
            continue

        counts[ticket.category_id] = counts.get(ticket.category_id, 0) + 1
        titles.setdefault(ticket.category_id, ticket.category_title or "Без названия")

    filters = [
        ArchiveCategoryFilter(
            id=ALL_ARCHIVE_CATEGORIES_ID,
            title="Все темы",
            ticket_count=counts[ALL_ARCHIVE_CATEGORIES_ID],
        )
    ]

    if UNCATEGORIZED_ARCHIVE_CATEGORY_ID in counts:
        filters.append(
            ArchiveCategoryFilter(
                id=UNCATEGORIZED_ARCHIVE_CATEGORY_ID,
                title=titles[UNCATEGORIZED_ARCHIVE_CATEGORY_ID],
                ticket_count=counts[UNCATEGORIZED_ARCHIVE_CATEGORY_ID],
            )
        )

    category_items = [
        ArchiveCategoryFilter(
            id=category_id,
            title=titles[category_id],
            ticket_count=counts[category_id],
        )
        for category_id in counts
        if category_id not in {ALL_ARCHIVE_CATEGORIES_ID, UNCATEGORIZED_ARCHIVE_CATEGORY_ID}
    ]
    category_items.sort(key=lambda item: (item.title.lower(), item.id))
    filters.extend(category_items)
    return tuple(filters)


def filter_archived_tickets(
    *,
    tickets: tuple[HistoricalTicketSummary, ...] | list[HistoricalTicketSummary],
    category_id: int,
) -> list[HistoricalTicketSummary]:
    if category_id == ALL_ARCHIVE_CATEGORIES_ID:
        return list(tickets)
    if category_id == UNCATEGORIZED_ARCHIVE_CATEGORY_ID:
        return [ticket for ticket in tickets if ticket.category_id is None]
    return [ticket for ticket in tickets if ticket.category_id == category_id]


def resolve_archive_category_title(
    *,
    filters: tuple[ArchiveCategoryFilter, ...] | list[ArchiveCategoryFilter],
    category_id: int,
) -> str | None:
    if category_id == ALL_ARCHIVE_CATEGORIES_ID:
        return None
    for item in filters:
        if item.id == category_id:
            return item.title
    return None
