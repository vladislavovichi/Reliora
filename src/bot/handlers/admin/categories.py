from __future__ import annotations

from aiogram import Router

from bot.handlers.admin.category_browser import router as browser_router
from bot.handlers.admin.category_mutations import router as mutations_router

router = Router(name="admin_categories")
router.include_router(browser_router)
router.include_router(mutations_router)
