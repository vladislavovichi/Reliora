from aiogram import Dispatcher

from bot.routers import build_root_router


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(build_root_router())
    return dispatcher
