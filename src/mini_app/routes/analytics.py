from __future__ import annotations

# ruff: noqa: B008
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from starlette.requests import Request
from starlette.responses import Response

from mini_app.context import MiniAppAuthenticatedContext, require_operator_context
from mini_app.request_parsing import parse_analytics_window
from mini_app.responses import MiniAppJSONResponse, json_response
from mini_app.routes.exports import export_analytics_response


def build_analytics_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/analytics", response_class=MiniAppJSONResponse)
    async def get_analytics(
        request: Request,
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        window = parse_analytics_window(urlparse(str(request.url)))
        return json_response(await context.gateway.get_analytics(user=context.user, window=window))

    @router.get("/api/analytics/export")
    async def export_analytics(
        request: Request,
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> Response:
        return await export_analytics_response(
            gateway=context.gateway,
            user=context.user,
            parsed=urlparse(str(request.url)),
        )

    return router
