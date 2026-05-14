from __future__ import annotations

# ruff: noqa: B008
from fastapi import APIRouter, Depends

from mini_app.context import MiniAppAuthenticatedContext, load_mini_app_session
from mini_app.responses import MiniAppJSONResponse, json_response


def build_session_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/session", response_class=MiniAppJSONResponse)
    async def get_session(
        context: MiniAppAuthenticatedContext = Depends(load_mini_app_session),
    ) -> MiniAppJSONResponse:
        return json_response(
            {
                **context.session,
                "launch": {
                    "source": context.launch.source,
                    "client_source": context.launch.client_source,
                },
            }
        )

    return router
