from __future__ import annotations

import re
from collections.abc import Sequence

from application.use_cases.tickets.summaries import (
    CategoryManagementError,
    TicketCategorySummary,
)
from domain.contracts.repositories import TicketCategoryRepository

_CYRILLIC_TRANSLITERATION = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)


class ListTicketCategoriesUseCase:
    def __init__(self, ticket_category_repository: TicketCategoryRepository) -> None:
        self.ticket_category_repository = ticket_category_repository

    async def __call__(self, *, include_inactive: bool = False) -> Sequence[TicketCategorySummary]:
        categories = await self.ticket_category_repository.list_all(
            include_inactive=include_inactive
        )
        return [
            TicketCategorySummary(
                id=category.id,
                code=category.code,
                title=category.title,
                is_active=category.is_active,
                sort_order=category.sort_order,
            )
            for category in categories
        ]


class GetTicketCategoryUseCase:
    def __init__(self, ticket_category_repository: TicketCategoryRepository) -> None:
        self.ticket_category_repository = ticket_category_repository

    async def __call__(self, *, category_id: int) -> TicketCategorySummary | None:
        category = await self.ticket_category_repository.get_by_id(category_id=category_id)
        if category is None:
            return None
        return TicketCategorySummary(
            id=category.id,
            code=category.code,
            title=category.title,
            is_active=category.is_active,
            sort_order=category.sort_order,
        )


class CreateTicketCategoryUseCase:
    def __init__(self, ticket_category_repository: TicketCategoryRepository) -> None:
        self.ticket_category_repository = ticket_category_repository

    async def __call__(self, *, title: str) -> TicketCategorySummary:
        normalized_title = _normalize_category_title(title)
        code = await _build_unique_code(
            ticket_category_repository=self.ticket_category_repository,
            title=normalized_title,
        )
        category = await self.ticket_category_repository.create(
            code=code,
            title=normalized_title,
            sort_order=await self.ticket_category_repository.get_next_sort_order(),
        )
        return TicketCategorySummary(
            id=category.id,
            code=category.code,
            title=category.title,
            is_active=category.is_active,
            sort_order=category.sort_order,
        )


class UpdateTicketCategoryTitleUseCase:
    def __init__(self, ticket_category_repository: TicketCategoryRepository) -> None:
        self.ticket_category_repository = ticket_category_repository

    async def __call__(self, *, category_id: int, title: str) -> TicketCategorySummary | None:
        category = await self.ticket_category_repository.update_title(
            category_id=category_id,
            title=_normalize_category_title(title),
        )
        if category is None:
            return None
        return TicketCategorySummary(
            id=category.id,
            code=category.code,
            title=category.title,
            is_active=category.is_active,
            sort_order=category.sort_order,
        )


class SetTicketCategoryActiveUseCase:
    def __init__(self, ticket_category_repository: TicketCategoryRepository) -> None:
        self.ticket_category_repository = ticket_category_repository

    async def __call__(
        self,
        *,
        category_id: int,
        is_active: bool,
    ) -> TicketCategorySummary | None:
        category = await self.ticket_category_repository.set_active(
            category_id=category_id,
            is_active=is_active,
        )
        if category is None:
            return None
        return TicketCategorySummary(
            id=category.id,
            code=category.code,
            title=category.title,
            is_active=category.is_active,
            sort_order=category.sort_order,
        )


def _normalize_category_title(title: str) -> str:
    normalized = " ".join(title.strip().split())
    if not normalized:
        raise CategoryManagementError("Название темы не должно быть пустым.")
    return normalized[:120]


async def _build_unique_code(
    *,
    ticket_category_repository: TicketCategoryRepository,
    title: str,
) -> str:
    base_code = _slugify_category_code(title)
    candidate = base_code
    suffix = 2
    while await ticket_category_repository.get_by_code(code=candidate) is not None:
        candidate = f"{base_code}-{suffix}"
        suffix += 1
    return candidate


def _slugify_category_code(title: str) -> str:
    latin = title.strip().lower().translate(_CYRILLIC_TRANSLITERATION)
    slug = re.sub(r"[^a-z0-9]+", "-", latin).strip("-")
    return slug[:48] or "topic"
