from __future__ import annotations

# ruff: noqa: B008
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends
from starlette.requests import Request
from starlette.responses import Response

from application.contracts.actors import OperatorIdentity
from mini_app.context import MiniAppAuthenticatedContext, require_operator_context
from mini_app.request_parsing import (
    AssignTicketPayload,
    MiniAppRouteNotFound,
    TicketNotePayload,
    parse_positive_int_path,
    parse_ticket_public_id,
    read_json_model,
)
from mini_app.responses import MiniAppJSONResponse, json_response
from mini_app.routes.exports import export_ticket_response


def build_ticket_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/tickets/{ticket_public_id}", response_class=MiniAppJSONResponse)
    async def get_ticket_workspace(
        ticket_public_id: str,
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        parsed_ticket_id = _require_ticket_public_id(ticket_public_id)
        return json_response(
            await context.gateway.get_ticket_workspace(
                user=context.user,
                ticket_public_id=parsed_ticket_id,
            )
        )

    @router.post("/api/tickets/{ticket_public_id}/take", response_class=MiniAppJSONResponse)
    async def take_ticket(
        ticket_public_id: str,
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        parsed_ticket_id = _require_ticket_public_id(ticket_public_id)
        return json_response(
            await context.gateway.take_ticket(user=context.user, ticket_public_id=parsed_ticket_id)
        )

    @router.post("/api/tickets/{ticket_public_id}/close", response_class=MiniAppJSONResponse)
    async def close_ticket(
        ticket_public_id: str,
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        parsed_ticket_id = _require_ticket_public_id(ticket_public_id)
        return json_response(
            await context.gateway.close_ticket(user=context.user, ticket_public_id=parsed_ticket_id)
        )

    @router.post("/api/tickets/{ticket_public_id}/escalate", response_class=MiniAppJSONResponse)
    async def escalate_ticket(
        ticket_public_id: str,
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        parsed_ticket_id = _require_ticket_public_id(ticket_public_id)
        return json_response(
            await context.gateway.escalate_ticket(
                user=context.user,
                ticket_public_id=parsed_ticket_id,
            )
        )

    @router.post("/api/tickets/{ticket_public_id}/assign", response_class=MiniAppJSONResponse)
    async def assign_ticket(
        ticket_public_id: str,
        request: Request,
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        parsed_ticket_id = _require_ticket_public_id(ticket_public_id)
        payload = await read_json_model(request, AssignTicketPayload)
        operator = OperatorIdentity(
            telegram_user_id=payload.telegram_user_id,
            display_name=payload.display_name,
            username=payload.username,
        )
        return json_response(
            await context.gateway.assign_ticket(
                user=context.user,
                ticket_public_id=parsed_ticket_id,
                operator_identity=operator,
            )
        )

    @router.post("/api/tickets/{ticket_public_id}/notes", response_class=MiniAppJSONResponse)
    async def add_note(
        ticket_public_id: str,
        request: Request,
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        parsed_ticket_id = _require_ticket_public_id(ticket_public_id)
        payload = await read_json_model(request, TicketNotePayload)
        return json_response(
            await context.gateway.add_note(
                user=context.user,
                ticket_public_id=parsed_ticket_id,
                text=payload.text,
            )
        )

    @router.post("/api/tickets/{ticket_public_id}/ai-summary", response_class=MiniAppJSONResponse)
    async def refresh_ticket_ai_summary(
        ticket_public_id: str,
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        parsed_ticket_id = _require_ticket_public_id(ticket_public_id)
        return json_response(
            await context.gateway.refresh_ticket_ai_summary(
                user=context.user,
                ticket_public_id=parsed_ticket_id,
            )
        )

    @router.post(
        "/api/tickets/{ticket_public_id}/ai-reply-draft",
        response_class=MiniAppJSONResponse,
    )
    async def generate_ticket_reply_draft(
        ticket_public_id: str,
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        parsed_ticket_id = _require_ticket_public_id(ticket_public_id)
        return json_response(
            await context.gateway.generate_ticket_reply_draft(
                user=context.user,
                ticket_public_id=parsed_ticket_id,
            )
        )

    @router.post(
        "/api/tickets/{ticket_public_id}/macros/{macro_id}", response_class=MiniAppJSONResponse
    )
    async def apply_macro(
        ticket_public_id: str,
        macro_id: str,
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> MiniAppJSONResponse:
        parsed_ticket_id = _require_ticket_public_id(ticket_public_id)
        parsed_macro_id = parse_positive_int_path(macro_id)
        if parsed_macro_id is None:
            raise MiniAppRouteNotFound
        return json_response(
            await context.gateway.apply_macro(
                user=context.user,
                ticket_public_id=parsed_ticket_id,
                macro_id=parsed_macro_id,
            )
        )

    @router.get("/api/tickets/{ticket_public_id}/export")
    async def export_ticket(
        ticket_public_id: str,
        request: Request,
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> Response:
        parsed_ticket_id = _require_ticket_public_id(ticket_public_id)
        return await export_ticket_response(
            gateway=context.gateway,
            user=context.user,
            ticket_public_id=parsed_ticket_id,
            parsed=urlparse(str(request.url)),
        )

    return router


def _require_ticket_public_id(raw_value: str) -> UUID:
    parsed_ticket_id = parse_ticket_public_id(raw_value)
    if parsed_ticket_id is None:
        raise MiniAppRouteNotFound
    return parsed_ticket_id
