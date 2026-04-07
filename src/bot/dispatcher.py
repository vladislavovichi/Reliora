from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.types import ErrorEvent

from bot.middlewares.authorization import AuthorizationMiddleware
from bot.middlewares.context import UpdateContextMiddleware
from bot.routers import build_root_router
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from infrastructure.config.settings import BotConfig, Settings


def build_bot(config: BotConfig) -> Bot:
    return Bot(token=config.token.strip())


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
    dispatcher.message.outer_middleware(authorization_middleware)
    dispatcher.callback_query.outer_middleware(authorization_middleware)


def _register_lifecycle(dispatcher: Dispatcher) -> None:
    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)
    dispatcher.observers["error"].register(on_error)


async def on_startup(dispatcher: Dispatcher, bot: Bot, settings: Settings, **_: Any) -> None:
    logger = logging.getLogger(__name__)
    bot_info = await bot.get_me()
    logger.info(
        "Bot startup completed username=%s app=%s update_types=%s",
        bot_info.username,
        settings.app.name,
        ",".join(dispatcher.resolve_used_update_types()),
    )


async def on_shutdown(dispatcher: Dispatcher, bot: Bot, settings: Settings, **_: Any) -> None:
    logger = logging.getLogger(__name__)
    logger.info(
        "Bot shutdown completed bot_id=%s app=%s update_types=%s",
        bot.id,
        settings.app.name,
        ",".join(dispatcher.resolve_used_update_types()),
    )


async def on_error(event: ErrorEvent, **_: Any) -> bool:
    logger = logging.getLogger(__name__)
    logger.exception(
        "Unhandled Telegram update processing failed update_id=%s",
        event.update.update_id,
        exc_info=event.exception,
    )

    callback_query = event.update.callback_query
    if callback_query is not None:
        try:
            await callback_query.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
        except Exception:
            logger.exception(
                "Failed to send callback error response update_id=%s",
                event.update.update_id,
            )
        return True

    message = event.update.message
    if message is not None:
        try:
            await message.answer(SERVICE_UNAVAILABLE_TEXT)
        except Exception:
            logger.exception(
                "Failed to send message error response update_id=%s",
                event.update.update_id,
            )
        return True

    return True
