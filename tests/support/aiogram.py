from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Chat, Message, User


@dataclass(slots=True)
class MessageHarness:
    message: Message
    answer: AsyncMock
    edit_text: AsyncMock | None = None
    edit_reply_markup: AsyncMock | None = None


@dataclass(slots=True)
class CallbackHarness:
    callback: CallbackQuery
    answer: AsyncMock
    message: MessageHarness


def build_message_harness(
    *,
    text: str = "stub",
    user_id: int,
    chat_id: int | None = None,
    message_id: int = 1,
    with_edit_text: bool = False,
    with_edit_reply_markup: bool = False,
) -> MessageHarness:
    message = Message.model_construct(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat.model_construct(id=chat_id or user_id, type="private"),
        from_user=User.model_construct(id=user_id, is_bot=False, first_name="Test"),
        text=text,
    )
    answer = AsyncMock()
    edit_text = AsyncMock() if with_edit_text else None
    edit_reply_markup = AsyncMock() if with_edit_reply_markup else None
    object.__setattr__(message, "answer", answer)
    if edit_text is not None:
        object.__setattr__(message, "edit_text", edit_text)
    if edit_reply_markup is not None:
        object.__setattr__(message, "edit_reply_markup", edit_reply_markup)
    return MessageHarness(
        message=message,
        answer=answer,
        edit_text=edit_text,
        edit_reply_markup=edit_reply_markup,
    )


def build_callback_harness(
    *,
    data: str,
    user_id: int,
    message: MessageHarness | None = None,
    text: str = "stub",
    with_edit_text: bool = False,
    with_edit_reply_markup: bool = False,
) -> CallbackHarness:
    message_harness = message or build_message_harness(
        text=text,
        user_id=user_id,
        with_edit_text=with_edit_text,
        with_edit_reply_markup=with_edit_reply_markup,
    )
    callback = CallbackQuery.model_construct(
        id="callback-id",
        from_user=User.model_construct(id=user_id, is_bot=False, first_name="Test"),
        chat_instance="chat-instance",
        data=data,
        message=message_harness.message,
    )
    answer = AsyncMock()
    object.__setattr__(callback, "answer", answer)
    return CallbackHarness(callback=callback, answer=answer, message=message_harness)
