from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import MagicData, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.handlers.common.state_reset import reset_transient_state
from bot.handlers.user.states import UserFeedbackStates, UserIntakeStates, UserOperatorInviteStates
from bot.keyboards.reply.main_menu import build_main_menu
from bot.texts.buttons import CANCEL_BUTTON_TEXT
from bot.texts.categories import INTAKE_CANCELLED_TEXT
from bot.texts.feedback import TICKET_FEEDBACK_COMMENT_CANCELLED_TEXT
from bot.texts.operator_invites import INVITE_ONBOARDING_CANCELLED_TEXT
from domain.enums.roles import UserRole

router = Router(name="user_cancellation")


@router.message(
    MagicData(F.event_user_role == UserRole.USER),
    StateFilter(
        UserIntakeStates.choosing_category,
        UserIntakeStates.writing_message,
        UserFeedbackStates.writing_comment,
        UserOperatorInviteStates.writing_display_name,
        UserOperatorInviteStates.confirming_display_name,
    ),
    F.text == CANCEL_BUTTON_TEXT,
)
async def handle_user_cancel(
    message: Message,
    state: FSMContext,
) -> None:
    state_name, _ = await reset_transient_state(state)
    text = INTAKE_CANCELLED_TEXT
    if state_name == UserFeedbackStates.writing_comment.state:
        text = TICKET_FEEDBACK_COMMENT_CANCELLED_TEXT
    elif state_name in {
        UserOperatorInviteStates.writing_display_name.state,
        UserOperatorInviteStates.confirming_display_name.state,
    }:
        text = INVITE_ONBOARDING_CANCELLED_TEXT
    await message.answer(text, reply_markup=build_main_menu(UserRole.USER))
