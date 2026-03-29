from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class OperatorActionCallback(CallbackData, prefix="operator"):
    action: Literal["take", "reply", "close", "escalate", "reassign", "view"]
    ticket_public_id: str
