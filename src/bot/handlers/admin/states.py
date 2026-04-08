from aiogram.fsm.state import State, StatesGroup


class AdminOperatorStates(StatesGroup):
    adding_operator = State()


class AdminMacroStates(StatesGroup):
    creating_title = State()
    creating_body = State()
    creating_preview = State()
    editing_title = State()
    editing_body = State()


class AdminCategoryStates(StatesGroup):
    creating_title = State()
    editing_title = State()
