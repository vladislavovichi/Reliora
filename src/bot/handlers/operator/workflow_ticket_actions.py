from __future__ import annotations

from aiogram import Router

from bot.handlers.operator.workflow_ticket_exports import router as exports_router
from bot.handlers.operator.workflow_ticket_mutations import router as mutations_router
from bot.handlers.operator.workflow_ticket_notes import router as notes_router
from bot.handlers.operator.workflow_ticket_views import router as views_router

router = Router(name="operator_workflow_ticket_actions")
router.include_router(views_router)
router.include_router(notes_router)
router.include_router(exports_router)
router.include_router(mutations_router)
