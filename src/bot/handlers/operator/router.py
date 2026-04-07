from __future__ import annotations

from aiogram import Router

from bot.handlers.operator.navigation import router as navigation_router
from bot.handlers.operator.stats import router as stats_router
from bot.handlers.operator.tags import router as tags_router
from bot.handlers.operator.workflow import router as workflow_router

router = Router(name="operator")
router.include_router(navigation_router)
router.include_router(stats_router)
router.include_router(tags_router)
router.include_router(workflow_router)
