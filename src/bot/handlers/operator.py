from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.callbacks import OperatorActionCallback

router = Router(name="operator")


@router.message(Command("stats"))
async def handle_stats(message: Message) -> None:
    await message.answer(
        "Operator statistics are not connected yet. This command is a placeholder."
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "take"))
async def handle_take_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
) -> None:
    await _answer_operator_action(callback, callback_data.action)


@router.callback_query(OperatorActionCallback.filter(F.action == "reply"))
async def handle_reply_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
) -> None:
    await _answer_operator_action(callback, callback_data.action)


@router.callback_query(OperatorActionCallback.filter(F.action == "close"))
async def handle_close_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
) -> None:
    await _answer_operator_action(callback, callback_data.action)


@router.callback_query(OperatorActionCallback.filter(F.action == "escalate"))
async def handle_escalate_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
) -> None:
    await _answer_operator_action(callback, callback_data.action)


async def _answer_operator_action(callback: CallbackQuery, action: str) -> None:
    await callback.answer(f"Operator action '{action}' is not implemented yet.")

    if callback.message is not None:
        await callback.message.answer(
            f"Operator action '{action}' was received. Workflow logic will be added later."
        )
