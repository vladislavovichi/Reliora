from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from bot.formatters.categories import format_admin_category_details
from bot.formatters.macros import format_admin_macro_details
from bot.formatters.operator_admin_views import format_operator_list_response
from bot.handlers.admin.category_surfaces import build_admin_category_list_response
from bot.handlers.admin.macro_surfaces import build_admin_macro_list_response
from bot.handlers.admin.states import (
    AdminCategoryStates,
    AdminMacroStates,
    AdminOperatorStates,
)
from bot.handlers.operator.active_context import activate_ticket_for_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.handlers.operator.states import OperatorTicketStates
from bot.handlers.operator.ticket_surfaces import send_ticket_details
from bot.keyboards.inline.admin import build_operator_management_markup
from bot.keyboards.inline.categories import build_admin_category_detail_markup
from bot.keyboards.inline.macros import build_admin_macro_detail_markup
from bot.texts.buttons import CANCEL_BUTTON_TEXT
from bot.texts.operator import OPERATOR_ACTION_CANCELLED_TEXT, OPERATOR_ACTION_IDLE_TEXT
from infrastructure.config.settings import Settings
from infrastructure.redis.contracts import (
    OperatorActiveTicketStore,
    TicketLiveSessionStore,
)

MACRO_CREATE_STATE_NAMES = {
    AdminMacroStates.creating_title.state,
    AdminMacroStates.creating_body.state,
    AdminMacroStates.creating_preview.state,
}
MACRO_EDIT_STATE_NAMES = {
    AdminMacroStates.editing_title.state,
    AdminMacroStates.editing_body.state,
}
CATEGORY_CREATE_STATE_NAMES = {
    AdminCategoryStates.creating_title.state,
}
CATEGORY_EDIT_STATE_NAMES = {
    AdminCategoryStates.editing_title.state,
}
OPERATOR_TICKET_STATE_NAMES = {
    OperatorTicketStates.replying.state,
    OperatorTicketStates.reassigning.state,
}

router = Router(name="operator_navigation_cancellation")


@router.message(F.text == CANCEL_BUTTON_TEXT)
async def handle_cancel(
    message: Message,
    state: FSMContext,
    settings: Settings,
    helpdesk_service_factory: HelpdeskServiceFactory,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
) -> None:
    state_name = await state.get_state()
    if state_name is None:
        await message.answer(OPERATOR_ACTION_IDLE_TEXT)
        return

    state_data = await state.get_data()
    await state.clear()
    await message.answer(OPERATOR_ACTION_CANCELLED_TEXT)
    if message.from_user is None:
        return

    if state_name in OPERATOR_TICKET_STATE_NAMES:
        await _restore_ticket_after_cancel(
            message=message,
            state_data=state_data,
            helpdesk_service_factory=helpdesk_service_factory,
            operator_active_ticket_store=operator_active_ticket_store,
            ticket_live_session_store=ticket_live_session_store,
        )
        return
    if state_name == AdminOperatorStates.adding_operator.state:
        await _restore_operator_directory_after_cancel(
            message=message,
            settings=settings,
            helpdesk_service_factory=helpdesk_service_factory,
        )
        return
    if state_name in MACRO_CREATE_STATE_NAMES:
        await _restore_macro_list_after_cancel(
            message=message,
            state_data=state_data,
            helpdesk_service_factory=helpdesk_service_factory,
        )
        return
    if state_name in MACRO_EDIT_STATE_NAMES:
        await _restore_macro_details_after_cancel(
            message=message,
            state_data=state_data,
            helpdesk_service_factory=helpdesk_service_factory,
        )
        return
    if state_name in CATEGORY_CREATE_STATE_NAMES:
        await _restore_category_list_after_cancel(
            message=message,
            state_data=state_data,
            helpdesk_service_factory=helpdesk_service_factory,
        )
        return
    if state_name in CATEGORY_EDIT_STATE_NAMES:
        await _restore_category_details_after_cancel(
            message=message,
            state_data=state_data,
            helpdesk_service_factory=helpdesk_service_factory,
        )


async def _restore_ticket_after_cancel(
    *,
    message: Message,
    state_data: dict[str, object],
    helpdesk_service_factory: HelpdeskServiceFactory,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
) -> None:
    ticket_public_id_value = state_data.get("ticket_public_id")
    ticket_public_id = parse_ticket_public_id(
        ticket_public_id_value if isinstance(ticket_public_id_value, str) else None
    )
    if ticket_public_id is None or message.from_user is None:
        return

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor_telegram_user_id=message.from_user.id,
        )

    if ticket_details is None:
        return

    is_active_context = await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=message.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )
    await send_ticket_details(
        message=message,
        ticket_details=ticket_details,
        is_active_context=is_active_context,
    )


async def _restore_operator_directory_after_cancel(
    *,
    message: Message,
    settings: Settings,
    helpdesk_service_factory: HelpdeskServiceFactory,
) -> None:
    if message.from_user is None:
        return

    async with helpdesk_service_factory() as helpdesk_service:
        operators = await helpdesk_service.list_operators(
            actor_telegram_user_id=message.from_user.id,
        )

    await message.answer(
        format_operator_list_response(
            operators=operators,
            super_admin_telegram_user_ids=settings.authorization.super_admin_telegram_user_ids,
        ),
        reply_markup=build_operator_management_markup(operators=operators),
    )


async def _restore_macro_list_after_cancel(
    *,
    message: Message,
    state_data: dict[str, object],
    helpdesk_service_factory: HelpdeskServiceFactory,
) -> None:
    if message.from_user is None:
        return

    page = _parse_page(state_data.get("page"))
    async with helpdesk_service_factory() as helpdesk_service:
        macros = await helpdesk_service.list_macros(actor_telegram_user_id=message.from_user.id)

    text, markup = build_admin_macro_list_response(macros=macros, page=page)
    await message.answer(text, reply_markup=markup)


async def _restore_macro_details_after_cancel(
    *,
    message: Message,
    state_data: dict[str, object],
    helpdesk_service_factory: HelpdeskServiceFactory,
) -> None:
    if message.from_user is None:
        return

    macro_id = state_data.get("macro_id")
    page = _parse_page(state_data.get("page"))
    if not isinstance(macro_id, int):
        await _restore_macro_list_after_cancel(
            message=message,
            state_data=state_data,
            helpdesk_service_factory=helpdesk_service_factory,
        )
        return

    async with helpdesk_service_factory() as helpdesk_service:
        macro = await helpdesk_service.get_macro(
            macro_id=macro_id,
            actor_telegram_user_id=message.from_user.id,
        )
        if macro is None:
            macros = await helpdesk_service.list_macros(actor_telegram_user_id=message.from_user.id)
            text, markup = build_admin_macro_list_response(macros=macros, page=page)
            await message.answer(text, reply_markup=markup)
            return

    await message.answer(
        format_admin_macro_details(macro),
        reply_markup=build_admin_macro_detail_markup(
            macro_id=macro.id,
            page=page,
        ),
    )


def _parse_page(value: object) -> int:
    return value if isinstance(value, int) and value > 0 else 1


async def _restore_category_list_after_cancel(
    *,
    message: Message,
    state_data: dict[str, object],
    helpdesk_service_factory: HelpdeskServiceFactory,
) -> None:
    if message.from_user is None:
        return

    page = _parse_page(state_data.get("page"))
    async with helpdesk_service_factory() as helpdesk_service:
        categories = await helpdesk_service.list_ticket_categories(
            actor_telegram_user_id=message.from_user.id
        )

    text, markup = build_admin_category_list_response(categories=categories, page=page)
    await message.answer(text, reply_markup=markup)


async def _restore_category_details_after_cancel(
    *,
    message: Message,
    state_data: dict[str, object],
    helpdesk_service_factory: HelpdeskServiceFactory,
) -> None:
    if message.from_user is None:
        return

    category_id = state_data.get("category_id")
    page = _parse_page(state_data.get("page"))
    if not isinstance(category_id, int):
        await _restore_category_list_after_cancel(
            message=message,
            state_data=state_data,
            helpdesk_service_factory=helpdesk_service_factory,
        )
        return

    async with helpdesk_service_factory() as helpdesk_service:
        category = await helpdesk_service.get_ticket_category(
            category_id=category_id,
            actor_telegram_user_id=message.from_user.id,
        )
        if category is None:
            categories = await helpdesk_service.list_ticket_categories(
                actor_telegram_user_id=message.from_user.id
            )
            text, markup = build_admin_category_list_response(categories=categories, page=page)
            await message.answer(text, reply_markup=markup)
            return

    await message.answer(
        format_admin_category_details(category),
        reply_markup=build_admin_category_detail_markup(category=category, page=page),
    )
