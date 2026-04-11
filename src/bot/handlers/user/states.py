from aiogram.fsm.state import State, StatesGroup


class UserIntakeStates(StatesGroup):
    choosing_category = State()
    writing_message = State()


class UserFeedbackStates(StatesGroup):
    writing_comment = State()


class UserOperatorInviteStates(StatesGroup):
    writing_display_name = State()
    confirming_display_name = State()
