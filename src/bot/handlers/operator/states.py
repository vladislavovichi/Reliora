from aiogram.fsm.state import State, StatesGroup


class OperatorTicketStates(StatesGroup):
    replying = State()
    reassigning = State()
    writing_note = State()
