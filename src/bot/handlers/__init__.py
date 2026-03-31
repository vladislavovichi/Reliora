"""Bot handlers."""

from bot.handlers.admin.operators import router as admin_router
from bot.handlers.common.system import router as system_router
from bot.handlers.operator import router as operator_router
from bot.handlers.user.client import router as client_router

__all__ = [
    "admin_router",
    "client_router",
    "operator_router",
    "system_router",
]
