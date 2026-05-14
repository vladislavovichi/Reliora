from __future__ import annotations

# ruff: noqa: B008
from fastapi import APIRouter, Depends

from mini_app.context import MiniAppAuthenticatedContext, require_operator_context
from mini_app.responses import MiniAppJSONResponse, json_response


def build_queue_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/queue", response_class=MiniAppJSONResponse)
    async def list_queue(
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        return json_response(await context.gateway.list_queue(user=context.user))

    @router.post("/api/queue/take-next", response_class=MiniAppJSONResponse)
    async def take_next_ticket(
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        return json_response(await context.gateway.take_next_ticket(user=context.user))

    @router.get("/api/my-tickets", response_class=MiniAppJSONResponse)
    async def list_my_tickets(
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        return json_response(await context.gateway.list_my_tickets(user=context.user))

    @router.get("/api/archive", response_class=MiniAppJSONResponse)
    async def list_archive(
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        return json_response(await context.gateway.list_archive(user=context.user))

    return router
