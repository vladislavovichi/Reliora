from __future__ import annotations

# ruff: noqa: B008
from fastapi import APIRouter, Depends

from mini_app.context import MiniAppAuthenticatedContext, require_operator_context
from mini_app.responses import MiniAppJSONResponse, json_response


def build_dashboard_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/dashboard", response_class=MiniAppJSONResponse)
    async def get_dashboard(
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        return json_response(await context.gateway.get_dashboard(user=context.user))

    @router.get("/api/dashboard/operator", response_class=MiniAppJSONResponse)
    async def get_operator_dashboard(
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        return json_response(await context.gateway.get_operator_dashboard(user=context.user))

    return router
