from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class OperatorActionCallback(CallbackData, prefix="operator"):
    action: Literal["take", "reply", "close", "escalate", "reassign", "view"]
    ticket_public_id: str


class OperatorQueueCallback(CallbackData, prefix="operator_queue"):
    action: Literal["page", "noop"]
    page: int


class OperatorMacroCallback(CallbackData, prefix="operator_macro"):
    ticket_public_id: str
    macro_id: int


class AdminOperatorCallback(CallbackData, prefix="admin_operator"):
    action: Literal["refresh", "revoke", "confirm_revoke", "cancel_revoke"]
    telegram_user_id: int
