from __future__ import annotations

from aiogram import Router

from bot.handlers.admin.categories import router as categories_router
from bot.handlers.admin.macros import router as macros_router
from bot.handlers.admin.operator_directory import router as directory_router
from bot.handlers.admin.operator_mutations import router as mutations_router

router = Router(name="admin_operators")
router.include_router(categories_router)
router.include_router(macros_router)
router.include_router(directory_router)
router.include_router(mutations_router)
