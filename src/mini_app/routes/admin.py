from __future__ import annotations

# ruff: noqa: B008
from typing import Any

from fastapi import APIRouter, Depends
from starlette.requests import Request

from application.errors import ForbiddenError
from domain.enums.roles import UserRole
from mini_app.context import MiniAppAuthenticatedContext, require_operator_context
from mini_app.request_parsing import read_json_body
from mini_app.responses import MiniAppJSONResponse, json_response


async def require_admin_context(
    context: MiniAppAuthenticatedContext = Depends(require_operator_context),
) -> MiniAppAuthenticatedContext:
    require_admin(context.session)
    return context


def build_admin_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/operators", response_class=MiniAppJSONResponse)
    async def list_operators(
        context: MiniAppAuthenticatedContext = Depends(require_admin_context),
    ) -> MiniAppJSONResponse:
        return json_response(await context.gateway.list_operators(user=context.user))

    @router.get("/api/admin/ai-settings", response_class=MiniAppJSONResponse)
    async def get_ai_settings(
        context: MiniAppAuthenticatedContext = Depends(require_admin_context),
    ) -> MiniAppJSONResponse:
        return json_response(await context.gateway.get_ai_settings(user=context.user))

    @router.put("/api/admin/ai-settings", response_class=MiniAppJSONResponse)
    async def update_ai_settings(
        request: Request,
        context: MiniAppAuthenticatedContext = Depends(require_admin_context),
    ) -> MiniAppJSONResponse:
        payload = await read_json_body(request)
        return json_response(
            await context.gateway.update_ai_settings(
                user=context.user,
                payload=payload,
            )
        )

    @router.post("/api/admin/invites", response_class=MiniAppJSONResponse)
    async def create_operator_invite(
        context: MiniAppAuthenticatedContext = Depends(require_admin_context),
    ) -> MiniAppJSONResponse:
        return json_response(await context.gateway.create_operator_invite(user=context.user))

    return router


def require_admin(session: dict[str, Any]) -> None:
    if session["access"]["role"] != UserRole.SUPER_ADMIN.value:
        raise ForbiddenError("Доступно только суперадминистраторам.")
