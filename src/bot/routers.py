from __future__ import annotations

from aiogram import Router

from bot.handlers import client_router, operator_router, system_router


def build_root_router() -> Router:
    root_router = Router(name="root")
    root_router.include_router(system_router)
    root_router.include_router(operator_router)
    root_router.include_router(client_router)
    return root_router
