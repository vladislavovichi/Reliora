from __future__ import annotations

from aiogram.fsm.context import FSMContext


async def reset_transient_state(
    state: FSMContext,
) -> tuple[str | None, dict[str, object]]:
    state_name = await state.get_state()
    state_data = await state.get_data()
    set_data = getattr(state, "set_data", None)
    if callable(set_data):
        await set_data({})
    set_state = getattr(state, "set_state", None)
    if callable(set_state):
        await set_state(None)
    await state.clear()
    return state_name, dict(state_data)
