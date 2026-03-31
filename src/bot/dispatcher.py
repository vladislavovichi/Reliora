from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage

from bot.middlewares import AuthorizationMiddleware, UpdateContextMiddleware
from bot.routers import build_root_router
from infrastructure.config import BotConfig, Settings


def build_bot(config: BotConfig) -> Bot:
    return Bot(token=config.token)


def build_dispatcher(*, storage: BaseStorage, **workflow_data: Any) -> Dispatcher:
    dispatcher = Dispatcher(storage=storage)
    dispatcher.workflow_data.update(workflow_data)
    _register_middlewares(dispatcher)
    _register_lifecycle(dispatcher)
    dispatcher.include_router(build_root_router())
    return dispatcher


def _register_middlewares(dispatcher: Dispatcher) -> None:
    update_context_middleware = UpdateContextMiddleware()
    authorization_middleware = AuthorizationMiddleware()
    dispatcher.message.outer_middleware(update_context_middleware)
    dispatcher.callback_query.outer_middleware(update_context_middleware)
    dispatcher.message.middleware(authorization_middleware)
    dispatcher.callback_query.middleware(authorization_middleware)


def _register_lifecycle(dispatcher: Dispatcher) -> None:
    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)


async def on_startup(dispatcher: Dispatcher, bot: Bot, settings: Settings, **_: Any) -> None:
    logger = logging.getLogger(__name__)
    bot_info = await bot.get_me()
    logger.info(
        "Bot startup completed username=%s app=%s",
        bot_info.username,
        settings.app.name,
    )


async def on_shutdown(dispatcher: Dispatcher, bot: Bot, settings: Settings, **_: Any) -> None:
    logger = logging.getLogger(__name__)
    logger.info(
        "Bot shutdown completed bot_id=%s app=%s",
        bot.id,
        settings.app.name,
    )
