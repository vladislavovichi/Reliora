from __future__ import annotations

from aiogram import Router

from bot.handlers.admin.operators import router as admin_router
from bot.handlers.common.system import router as system_router
from bot.handlers.operator.router import router as operator_router
from bot.handlers.user.client import router as client_router
from bot.handlers.user.feedback import router as feedback_router
from bot.handlers.user.intake import router as intake_router
from bot.handlers.user.operator_invites import router as operator_invites_router


def build_root_router() -> Router:
    root_router = Router(name="root")
    root_router.include_router(system_router)
    root_router.include_router(admin_router)
    root_router.include_router(operator_router)
    root_router.include_router(operator_invites_router)
    root_router.include_router(intake_router)
    root_router.include_router(feedback_router)
    root_router.include_router(client_router)
    return root_router
