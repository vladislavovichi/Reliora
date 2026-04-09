from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class OperatorActionCallback(CallbackData, prefix="operator"):
    action: Literal[
        "take",
        "reply",
        "close",
        "escalate",
        "reassign",
        "view",
        "back",
        "macros",
        "tags",
        "more",
        "card",
    ]
    ticket_public_id: str


class ClientTicketCallback(CallbackData, prefix="client"):
    action: Literal["finish", "finish_confirm", "finish_cancel"]
    ticket_public_id: str


class ClientFeedbackCallback(CallbackData, prefix="client_feedback"):
    action: Literal["rate", "comment", "skip"]
    ticket_public_id: str
    rating: int


class ClientIntakeCallback(CallbackData, prefix="client_intake"):
    action: Literal["pick", "cancel"]
    category_id: int


class OperatorQueueCallback(CallbackData, prefix="operator_queue"):
    action: Literal["page", "noop"]
    scope: Literal["queue", "mine"]
    page: int


class OperatorMacroCallback(CallbackData, prefix="operator_macro"):
    action: Literal["page", "noop", "preview", "apply", "back", "ticket"]
    ticket_public_id: str
    macro_id: int
    page: int


class OperatorTagCallback(CallbackData, prefix="operator_tag"):
    action: Literal["toggle", "ticket"]
    ticket_public_id: str
    tag_id: int


class AdminOperatorCallback(CallbackData, prefix="admin_operator"):
    action: Literal[
        "refresh",
        "view",
        "add",
        "back_list",
        "revoke",
        "confirm_revoke",
        "cancel_revoke",
    ]
    telegram_user_id: int


class AdminMacroCallback(CallbackData, prefix="admin_macro"):
    action: Literal[
        "page",
        "noop",
        "view",
        "create",
        "back_list",
        "edit_title",
        "edit_body",
        "delete",
        "confirm_delete",
        "cancel_delete",
        "preview_save",
        "preview_edit",
        "preview_cancel",
    ]
    macro_id: int
    page: int


class AdminCategoryCallback(CallbackData, prefix="admin_category"):
    action: Literal[
        "page",
        "noop",
        "view",
        "create",
        "back_list",
        "edit_title",
        "enable",
        "disable",
    ]
    category_id: int
    page: int
