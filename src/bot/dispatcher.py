from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.middlewares import UpdateContextMiddleware
from bot.routers import build_root_router
from infrastructure.config import BotConfig, Settings


def build_bot(config: BotConfig) -> Bot:
    return Bot(token=config.token)


def build_dispatcher(**workflow_data: Any) -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.workflow_data.update(workflow_data)
    _register_middlewares(dispatcher)
    _register_lifecycle(dispatcher)
    dispatcher.include_router(build_root_router())
    return dispatcher


def _register_middlewares(dispatcher: Dispatcher) -> None:
    middleware = UpdateContextMiddleware()
    dispatcher.message.outer_middleware(middleware)
    dispatcher.callback_query.outer_middleware(middleware)


def _register_lifecycle(dispatcher: Dispatcher) -> None:
    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)


async def on_startup(
    dispatcher: Dispatcher, bot: Bot, settings: Settings, **_: Any
) -> None:
    logger = logging.getLogger(__name__)
    bot_info = await bot.get_me()
    logger.info(
        "Bot startup completed username=%s app=%s",
        bot_info.username,
        settings.app.name,
    )


async def on_shutdown(
    dispatcher: Dispatcher, bot: Bot, settings: Settings, **_: Any
) -> None:
    logger = logging.getLogger(__name__)
    logger.info(
        "Bot shutdown completed bot_id=%s app=%s",
        bot.id,
        settings.app.name,
    )
