from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from bot.callbacks import AdminCategoryCallback
from bot.handlers.admin.category_surfaces import (
    build_admin_category_list_response,
    edit_admin_category_details,
    edit_admin_category_list,
)
from bot.handlers.operator.common import respond_to_operator
from bot.texts.buttons import CATEGORIES_BUTTON_TEXT
from bot.texts.categories import (
    CATEGORY_DISABLED_TEXT,
    CATEGORY_ENABLED_TEXT,
    CATEGORY_LIST_UPDATED_TEXT,
    CATEGORY_NOT_FOUND_TEXT,
)
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from infrastructure.redis.contracts import GlobalRateLimiter, OperatorPresenceHelper

router = Router(name="admin_category_browser")


@router.message(F.text == CATEGORIES_BUTTON_TEXT)
async def handle_admin_categories(
    message: Message,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return
    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)
    await state.clear()

    async with helpdesk_service_factory() as helpdesk_service:
        categories = await helpdesk_service.list_ticket_categories(
            actor_telegram_user_id=message.from_user.id if message.from_user is not None else None
        )

    text, markup = build_admin_category_list_response(categories=categories, page=1)
    await message.answer(text, reply_markup=markup)


@router.callback_query(AdminCategoryCallback.filter(F.action == "page"))
async def handle_admin_category_page(
    callback: CallbackQuery,
    callback_data: AdminCategoryCallback,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    await state.clear()

    async with helpdesk_service_factory() as helpdesk_service:
        categories = await helpdesk_service.list_ticket_categories(
            actor_telegram_user_id=callback.from_user.id
        )

    await edit_admin_category_list(
        callback=callback,
        categories=categories,
        page=callback_data.page,
        answer_text=CATEGORY_LIST_UPDATED_TEXT,
    )


@router.callback_query(AdminCategoryCallback.filter(F.action == "noop"))
async def handle_admin_category_page_noop(
    callback: CallbackQuery,
    callback_data: AdminCategoryCallback,
) -> None:
    await callback.answer(f"Страница {callback_data.page}")


@router.callback_query(AdminCategoryCallback.filter(F.action == "view"))
async def handle_admin_category_view(
    callback: CallbackQuery,
    callback_data: AdminCategoryCallback,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    await state.clear()

    async with helpdesk_service_factory() as helpdesk_service:
        category = await helpdesk_service.get_ticket_category(
            category_id=callback_data.category_id,
            actor_telegram_user_id=callback.from_user.id,
        )

    if category is None:
        async with helpdesk_service_factory() as helpdesk_service:
            categories = await helpdesk_service.list_ticket_categories(
                actor_telegram_user_id=callback.from_user.id
            )
        await edit_admin_category_list(
            callback=callback,
            categories=categories,
            page=callback_data.page,
            answer_text=CATEGORY_NOT_FOUND_TEXT,
        )
        return

    await edit_admin_category_details(
        callback=callback,
        category=category,
        page=callback_data.page,
        answer_text=CATEGORY_LIST_UPDATED_TEXT,
    )


@router.callback_query(AdminCategoryCallback.filter(F.action == "back_list"))
async def handle_admin_category_back_list(
    callback: CallbackQuery,
    callback_data: AdminCategoryCallback,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    await state.clear()

    async with helpdesk_service_factory() as helpdesk_service:
        categories = await helpdesk_service.list_ticket_categories(
            actor_telegram_user_id=callback.from_user.id
        )

    await edit_admin_category_list(
        callback=callback,
        categories=categories,
        page=callback_data.page,
        answer_text=CATEGORY_LIST_UPDATED_TEXT,
    )


@router.callback_query(AdminCategoryCallback.filter(F.action.in_({"enable", "disable"})))
async def handle_admin_category_toggle(
    callback: CallbackQuery,
    callback_data: AdminCategoryCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    is_active = callback_data.action == "enable"

    async with helpdesk_service_factory() as helpdesk_service:
        category = await helpdesk_service.set_ticket_category_active(
            category_id=callback_data.category_id,
            is_active=is_active,
            actor_telegram_user_id=callback.from_user.id,
        )

    if category is None:
        async with helpdesk_service_factory() as helpdesk_service:
            categories = await helpdesk_service.list_ticket_categories(
                actor_telegram_user_id=callback.from_user.id
            )
        await edit_admin_category_list(
            callback=callback,
            categories=categories,
            page=callback_data.page,
            answer_text=CATEGORY_NOT_FOUND_TEXT,
        )
        return

    await edit_admin_category_details(
        callback=callback,
        category=category,
        page=callback_data.page,
        answer_text=CATEGORY_ENABLED_TEXT if is_active else CATEGORY_DISABLED_TEXT,
    )
