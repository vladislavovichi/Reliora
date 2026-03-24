from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot, Dispatcher

from bot.dispatcher import build_dispatcher
from infrastructure.config import Settings


@dataclass(slots=True)
class AppRuntime:
    settings: Settings
    dispatcher: Dispatcher
    bot: Bot


def build_runtime(settings: Settings) -> AppRuntime:
    if not settings.telegram.token:
        raise RuntimeError("TELEGRAM__TOKEN must be set when APP__DRY_RUN is false.")

    bot = Bot(token=settings.telegram.token)
    dispatcher = build_dispatcher()
    return AppRuntime(settings=settings, dispatcher=dispatcher, bot=bot)
