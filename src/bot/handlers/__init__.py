"""Bot handlers."""

from bot.handlers.client import router as client_router
from bot.handlers.operator import router as operator_router
from bot.handlers.system import router as system_router

__all__ = [
    "client_router",
    "operator_router",
    "system_router",
]
