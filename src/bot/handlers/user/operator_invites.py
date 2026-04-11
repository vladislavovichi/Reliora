from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import MagicData, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.operator_invites import OperatorInviteCodeError
from bot.adapters.helpdesk import build_operator_identity_from_parts
from bot.callbacks import OperatorInviteCallback
from bot.formatters.operator_admin_views import (
    format_operator_onboarding_confirmation,
    format_operator_onboarding_prompt,
)
from bot.handlers.user.states import UserOperatorInviteStates
from bot.keyboards.inline.operator_invites import build_operator_invite_confirmation_markup
from bot.keyboards.reply.main_menu import build_main_menu
from bot.texts.operator_invites import (
    INVITE_ONBOARDING_CONFIRMED_TEXT,
    INVITE_ONBOARDING_EDIT_TEXT,
    INVITE_ONBOARDING_NAME_INVALID_TEXT,
    build_invite_invalid_text,
    build_invite_welcome_text,
)
from domain.enums.roles import UserRole

router = Router(name="user_operator_invites")


async def start_operator_invite_onboarding(
    *,
    message: Message,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    code: str,
) -> bool:
    async with helpdesk_service_factory() as helpdesk_service:
        try:
            invite = await helpdesk_service.preview_operator_invite(code=code)
        except OperatorInviteCodeError as exc:
            await message.answer(build_invite_invalid_text(str(exc)))
            return False

    await state.set_state(UserOperatorInviteStates.writing_display_name)
    await state.update_data(
        operator_invite_code=code,
        operator_invite_expires_at=invite.expires_at.isoformat(),
    )
    await message.answer(
        format_operator_onboarding_prompt(
            deep_link_code=code,
            expires_at=invite.expires_at,
        )
    )
    return True


@router.message(
    StateFilter(UserOperatorInviteStates.writing_display_name),
    MagicData(F.event_user_role == UserRole.USER),
    F.text & ~F.text.startswith("/"),
)
async def handle_operator_invite_display_name(
    message: Message,
    state: FSMContext,
) -> None:
    display_name = _normalize_display_name(message.text)
    if display_name is None:
        await message.answer(INVITE_ONBOARDING_NAME_INVALID_TEXT)
        return

    await state.set_state(UserOperatorInviteStates.confirming_display_name)
    await state.update_data(operator_invite_display_name=display_name)
    await message.answer(
        format_operator_onboarding_confirmation(display_name=display_name),
        reply_markup=build_operator_invite_confirmation_markup(),
    )


@router.callback_query(
    StateFilter(UserOperatorInviteStates.confirming_display_name),
    MagicData(F.event_user_role == UserRole.USER),
    OperatorInviteCallback.filter(F.action == "edit"),
)
async def handle_operator_invite_edit(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    state_data = await state.get_data()
    expires_at = _load_expires_at(state_data)
    code = state_data.get("operator_invite_code")
    await state.set_state(UserOperatorInviteStates.writing_display_name)
    await callback.answer(INVITE_ONBOARDING_EDIT_TEXT)
    if not isinstance(callback.message, Message) or not isinstance(code, str) or expires_at is None:
        return
    await callback.message.edit_text(
        format_operator_onboarding_prompt(
            deep_link_code=code,
            expires_at=expires_at,
        ),
        reply_markup=None,
    )


@router.callback_query(
    StateFilter(UserOperatorInviteStates.confirming_display_name),
    MagicData(F.event_user_role == UserRole.USER),
    OperatorInviteCallback.filter(F.action == "confirm"),
)
async def handle_operator_invite_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
) -> None:
    if callback.from_user is None:
        return

    state_data = await state.get_data()
    code = state_data.get("operator_invite_code")
    display_name = state_data.get("operator_invite_display_name")
    if not isinstance(code, str) or not isinstance(display_name, str):
        await state.clear()
        await callback.answer("Сеанс приглашения устарел.", show_alert=True)
        return

    async with helpdesk_service_factory() as helpdesk_service:
        try:
            result = await helpdesk_service.redeem_operator_invite(
                code=code,
                operator=build_operator_identity_from_parts(
                    telegram_user_id=callback.from_user.id,
                    display_name=display_name,
                    username=callback.from_user.username,
                ),
            )
        except OperatorInviteCodeError as exc:
            await state.clear()
            await callback.answer(build_invite_invalid_text(str(exc)), show_alert=True)
            return

    await state.clear()
    await callback.answer(INVITE_ONBOARDING_CONFIRMED_TEXT)
    welcome_text = build_invite_welcome_text(result.operator.operator.display_name)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(welcome_text, reply_markup=None)
        await callback.message.answer(
            "Рабочее место оператора готово.",
            reply_markup=build_main_menu(UserRole.OPERATOR),
        )
        return


def _normalize_display_name(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = " ".join(text.split())
    if not normalized or len(normalized) > 64:
        return None
    return normalized


def _load_expires_at(state_data: dict[str, object]) -> datetime | None:
    raw = state_data.get("operator_invite_expires_at")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None
