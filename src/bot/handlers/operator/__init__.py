from aiogram import Router

from bot.handlers.operator.commands import router as commands_router
from bot.handlers.operator.stats import router as stats_router
from bot.handlers.operator.workflow import router as workflow_router

router = Router(name="operator")
router.include_router(commands_router)
router.include_router(stats_router)
router.include_router(workflow_router)

__all__ = ["router"]
