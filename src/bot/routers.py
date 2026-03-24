from aiogram import Router

from bot.handlers.system import router as system_router


def build_root_router() -> Router:
    root_router = Router(name="root")
    root_router.include_router(system_router)
    return root_router
