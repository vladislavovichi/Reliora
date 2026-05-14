from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode
from uuid import uuid4

import httpx

from application.errors import NotFoundError
from domain.enums.roles import UserRole
from infrastructure.config.settings import MiniAppConfig
from mini_app.auth import TelegramMiniAppUser
from mini_app.http import create_mini_app
from mini_app.responses import BinaryPayload

BOT_TOKEN = "123:ABC"


class StubGateway:
    def __init__(
        self,
        *,
        role: UserRole = UserRole.OPERATOR,
        dashboard_error: Exception | None = None,
        ticket_error: Exception | None = None,
    ) -> None:
        self.role = role
        self.dashboard_error = dashboard_error
        self.ticket_error = ticket_error
        self.calls: list[str] = []

    async def get_session(self, *, user: TelegramMiniAppUser) -> dict[str, object]:
        return {
            "access": {
                "telegram_user_id": user.telegram_user_id,
                "role": self.role.value,
            },
            "user": {"display_name": user.display_name},
        }

    async def get_dashboard(self, *, user: TelegramMiniAppUser) -> dict[str, object]:
        del user
        if self.dashboard_error is not None:
            raise self.dashboard_error
        return {"ok": True}

    async def list_queue(self, *, user: TelegramMiniAppUser) -> dict[str, object]:
        del user
        self.calls.append("list_queue")
        return {"items": [{"public_id": "queued-ticket", "status": "queued"}]}

    async def take_next_ticket(self, *, user: TelegramMiniAppUser) -> dict[str, object]:
        del user
        self.calls.append("take_next_ticket")
        return {
            "ticket": {
                "public_id": "next-ticket",
                "public_number": "#42",
                "status": "assigned",
                "created": "2026-04-20T10:00:00+00:00",
                "event_type": "general",
            }
        }

    async def list_my_tickets(self, *, user: TelegramMiniAppUser) -> dict[str, object]:
        del user
        self.calls.append("list_my_tickets")
        return {"items": [{"public_id": "my-ticket", "status": "assigned"}]}

    async def list_archive(self, *, user: TelegramMiniAppUser) -> dict[str, object]:
        del user
        self.calls.append("list_archive")
        return {"items": [{"public_id": "closed-ticket", "status": "closed"}]}

    async def get_ticket_workspace(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: object,
    ) -> dict[str, object]:
        del user, ticket_public_id
        if self.ticket_error is not None:
            raise self.ticket_error
        return {"ticket": {"public_id": "ticket"}}

    async def take_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: object,
    ) -> dict[str, object]:
        del user, ticket_public_id
        self.calls.append("take_ticket")
        return {"public_id": "ticket", "status": "assigned"}

    async def close_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: object,
    ) -> dict[str, object]:
        del user, ticket_public_id
        self.calls.append("close_ticket")
        return {"public_id": "ticket", "status": "closed"}

    async def escalate_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: object,
    ) -> dict[str, object]:
        del user, ticket_public_id
        self.calls.append("escalate_ticket")
        return {"public_id": "ticket", "status": "escalated"}

    async def assign_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: object,
        operator_identity: object,
    ) -> dict[str, object]:
        del user, ticket_public_id
        self.calls.append("assign_ticket")
        return {"operator": {"display_name": operator_identity.display_name}}

    async def add_note(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: object,
        text: str,
    ) -> dict[str, object]:
        del user, ticket_public_id
        self.calls.append("add_note")
        return {"note": {"text": text}}

    async def apply_macro(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: object,
        macro_id: int,
    ) -> dict[str, object]:
        del user, ticket_public_id
        self.calls.append("apply_macro")
        return {"macro": {"id": macro_id}}

    async def refresh_ticket_ai_summary(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: object,
    ) -> dict[str, object]:
        del user, ticket_public_id
        self.calls.append("refresh_ticket_ai_summary")
        return {"available": True, "short_summary": "Кратко"}

    async def generate_ticket_reply_draft(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: object,
    ) -> dict[str, object]:
        del user, ticket_public_id
        self.calls.append("generate_ticket_reply_draft")
        return {"available": True, "reply_text": "Здравствуйте!"}

    async def export_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: object,
        format: object,
    ) -> BinaryPayload:
        del user, ticket_public_id, format
        self.calls.append("export_ticket")
        return BinaryPayload(
            filename="ticket.html",
            content_type="text/html; charset=utf-8",
            content=b"<html>ticket</html>",
        )

    async def get_analytics(
        self,
        *,
        user: TelegramMiniAppUser,
        window: object,
    ) -> dict[str, object]:
        del user
        self.calls.append(f"get_analytics:{window}")
        return {"snapshot": {"window": "7d", "total_open_tickets": 3}}

    async def export_analytics(
        self,
        *,
        user: TelegramMiniAppUser,
        window: object,
        section: object,
        format: object,
    ) -> BinaryPayload:
        del user, window, section, format
        self.calls.append("export_analytics")
        return BinaryPayload(
            filename="analytics.csv",
            content_type="text/csv; charset=utf-8",
            content=b"metric,value\nopen,3\n",
        )

    async def list_operators(self, *, user: TelegramMiniAppUser) -> dict[str, object]:
        del user
        self.calls.append("list_operators")
        return {"items": [{"telegram_user_id": 1001, "display_name": "Operator"}]}

    async def get_ai_settings(self, *, user: TelegramMiniAppUser) -> dict[str, object]:
        del user
        self.calls.append("get_ai_settings")
        return {"settings": {"ai_reply_drafts_enabled": True}}

    async def update_ai_settings(
        self,
        *,
        user: TelegramMiniAppUser,
        payload: dict[str, object],
    ) -> dict[str, object]:
        del user
        self.calls.append("update_ai_settings")
        return {"settings": payload}

    async def create_operator_invite(self, *, user: TelegramMiniAppUser) -> dict[str, object]:
        del user
        self.calls.append("create_operator_invite")
        return {"invite": {"code": "invite-code", "telegram_deep_link": None}}


def test_http_session_accepts_valid_telegram_init_data() -> None:
    status, payload = request_json(
        gateway=StubGateway(),
        path="/api/session",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 200
    assert payload["access"]["role"] == "operator"
    assert payload["user"]["display_name"] == "Анна Смирнова"


def test_http_rejects_invalid_telegram_init_data() -> None:
    status, payload = request_json(
        gateway=StubGateway(),
        path="/api/session",
        init_data="auth_date=1&hash=bad",
    )

    assert status == 401
    assert payload["code"] in {"malformed_init_data", "invalid_signature"}


def test_http_rejects_expired_telegram_init_data() -> None:
    status, payload = request_json(
        gateway=StubGateway(),
        path="/api/session",
        init_data=build_init_data(auth_date=datetime.now(UTC) - timedelta(minutes=2)),
        init_data_ttl_seconds=1,
    )

    assert status == 401
    assert payload["code"] == "expired_init_data"


def test_http_forbids_user_role_from_operator_dashboard() -> None:
    status, payload = request_json(
        gateway=StubGateway(role=UserRole.USER),
        path="/api/dashboard",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 403
    assert payload["code"] == "access_denied"


def test_http_unknown_api_route_still_requires_auth() -> None:
    status, payload = request_json(
        gateway=StubGateway(),
        path="/api/unknown",
        init_data="auth_date=1&hash=bad",
    )

    assert status == 401
    assert payload["code"] in {"malformed_init_data", "invalid_signature"}


def test_http_unknown_api_route_rejects_plain_user_before_not_found() -> None:
    status, payload = request_json(
        gateway=StubGateway(role=UserRole.USER),
        path="/api/unknown",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 403
    assert payload["code"] == "access_denied"


def test_http_maps_missing_ticket_to_not_found() -> None:
    status, payload = request_json(
        gateway=StubGateway(ticket_error=NotFoundError("Заявка не найдена.")),
        path=f"/api/tickets/{uuid4()}",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 404
    assert payload == {"error": "Заявка не найдена.", "code": "not_found"}


def test_http_maps_backend_unavailable_to_safe_response() -> None:
    status, payload = request_json(
        gateway=StubGateway(dashboard_error=ConnectionError("backend token rejected")),
        path="/api/dashboard",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 503
    assert payload["code"] == "backend_unavailable"
    assert "token" not in payload["error"].lower()


def test_http_routes_queue_surfaces() -> None:
    gateway = StubGateway()
    init_data = build_init_data(auth_date=datetime.now(UTC))

    queue_status, queue_payload = request_json(
        gateway=gateway,
        path="/api/queue",
        init_data=init_data,
    )
    take_status, take_payload = request_json(
        gateway=gateway,
        method="POST",
        path="/api/queue/take-next",
        init_data=init_data,
    )
    mine_status, mine_payload = request_json(
        gateway=gateway,
        path="/api/my-tickets",
        init_data=init_data,
    )
    archive_status, archive_payload = request_json(
        gateway=gateway,
        path="/api/archive",
        init_data=init_data,
    )

    assert queue_status == 200
    assert queue_payload["items"][0]["public_id"] == "queued-ticket"
    assert take_status == 200
    assert take_payload["ticket"]["public_number"] == "#42"
    assert mine_status == 200
    assert mine_payload["items"][0]["public_id"] == "my-ticket"
    assert archive_status == 200
    assert archive_payload["items"][0]["status"] == "closed"
    assert gateway.calls == [
        "list_queue",
        "take_next_ticket",
        "list_my_tickets",
        "list_archive",
    ]


def test_http_routes_ticket_details_through_gateway() -> None:
    gateway = StubGateway()

    status, payload = request_json(
        gateway=gateway,
        path=f"/api/tickets/{uuid4()}",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 200
    assert payload == {"ticket": {"public_id": "ticket"}}


def test_http_routes_ticket_action_through_gateway_without_handler_call() -> None:
    ticket_id = uuid4()
    gateway = StubGateway()

    status, payload = request_json(
        gateway=gateway,
        method="POST",
        path=f"/api/tickets/{ticket_id}/take",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 200
    assert payload == {"public_id": "ticket", "status": "assigned"}
    assert gateway.calls == ["take_ticket"]


def test_http_routes_ticket_mutations_with_json_payloads() -> None:
    ticket_id = uuid4()
    gateway = StubGateway()
    init_data = build_init_data(auth_date=datetime.now(UTC))

    close_status, close_payload = request_json(
        gateway=gateway,
        method="POST",
        path=f"/api/tickets/{ticket_id}/close",
        init_data=init_data,
    )
    assign_status, assign_payload = request_json(
        gateway=gateway,
        method="POST",
        path=f"/api/tickets/{ticket_id}/assign",
        init_data=init_data,
        body=json.dumps(
            {
                "telegram_user_id": 2002,
                "display_name": "  Иван   Петров ",
                "username": "ivan",
            }
        ).encode(),
    )
    note_status, note_payload = request_json(
        gateway=gateway,
        method="POST",
        path=f"/api/tickets/{ticket_id}/notes",
        init_data=init_data,
        body=json.dumps({"text": "  Проверить оплату  "}).encode(),
    )
    macro_status, macro_payload = request_json(
        gateway=gateway,
        method="POST",
        path=f"/api/tickets/{ticket_id}/macros/7",
        init_data=init_data,
    )

    assert close_status == 200
    assert close_payload["status"] == "closed"
    assert assign_status == 200
    assert assign_payload["operator"]["display_name"] == "Иван Петров"
    assert note_status == 200
    assert note_payload["note"]["text"] == "Проверить оплату"
    assert macro_status == 200
    assert macro_payload["macro"]["id"] == 7
    assert gateway.calls == ["close_ticket", "assign_ticket", "add_note", "apply_macro"]


def test_http_routes_ai_summary_and_reply_draft() -> None:
    ticket_id = uuid4()
    gateway = StubGateway()

    summary_status, summary_payload = request_json(
        gateway=gateway,
        method="POST",
        path=f"/api/tickets/{ticket_id}/ai-summary",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )
    draft_status, draft_payload = request_json(
        gateway=gateway,
        method="POST",
        path=f"/api/tickets/{ticket_id}/ai-reply-draft",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert summary_status == 200
    assert summary_payload["short_summary"] == "Кратко"
    assert draft_status == 200
    assert draft_payload["reply_text"] == "Здравствуйте!"
    assert gateway.calls == ["refresh_ticket_ai_summary", "generate_ticket_reply_draft"]


def test_http_routes_ticket_export_as_binary_response() -> None:
    ticket_id = uuid4()
    gateway = StubGateway()

    status, headers, body = request_raw(
        gateway=gateway,
        path=f"/api/tickets/{ticket_id}/export?format=html",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert headers["Content-Disposition"] == 'attachment; filename="ticket.html"'
    assert body == b"<html>ticket</html>"
    assert gateway.calls == ["export_ticket"]


def test_http_routes_analytics_and_export() -> None:
    gateway = StubGateway()
    init_data = build_init_data(auth_date=datetime.now(UTC))

    status, payload = request_json(
        gateway=gateway,
        path="/api/analytics?window=7d",
        init_data=init_data,
    )
    export_status, export_headers, export_body = request_raw(
        gateway=gateway,
        path="/api/analytics/export?window=7d&section=overview&format=csv",
        init_data=init_data,
    )

    assert status == 200
    assert payload["snapshot"]["total_open_tickets"] == 3
    assert export_status == 200
    assert export_headers["Content-Type"] == "text/csv; charset=utf-8"
    assert export_headers["Content-Disposition"] == 'attachment; filename="analytics.csv"'
    assert export_body == b"metric,value\nopen,3\n"
    assert gateway.calls == ["get_analytics:7d", "export_analytics"]


def test_http_restricts_admin_routes_to_super_admin() -> None:
    status, payload = request_json(
        gateway=StubGateway(role=UserRole.OPERATOR),
        path="/api/admin/operators",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 403
    assert payload == {"error": "Доступно только суперадминистраторам.", "code": "access_denied"}


def test_http_allows_super_admin_route() -> None:
    gateway = StubGateway(role=UserRole.SUPER_ADMIN)

    status, payload = request_json(
        gateway=gateway,
        path="/api/admin/operators",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 200
    assert payload["items"][0]["telegram_user_id"] == 1001
    assert gateway.calls == ["list_operators"]


def test_http_routes_admin_ai_settings_and_invites_for_super_admin() -> None:
    gateway = StubGateway(role=UserRole.SUPER_ADMIN)
    init_data = build_init_data(auth_date=datetime.now(UTC))

    settings_status, settings_payload = request_json(
        gateway=gateway,
        path="/api/admin/ai-settings",
        init_data=init_data,
    )
    update_status, update_payload = request_json(
        gateway=gateway,
        method="PUT",
        path="/api/admin/ai-settings",
        init_data=init_data,
        body=json.dumps({"ai_reply_drafts_enabled": False}).encode(),
    )
    invite_status, invite_payload = request_json(
        gateway=gateway,
        method="POST",
        path="/api/admin/invites",
        init_data=init_data,
    )

    assert settings_status == 200
    assert settings_payload["settings"]["ai_reply_drafts_enabled"] is True
    assert update_status == 200
    assert update_payload["settings"]["ai_reply_drafts_enabled"] is False
    assert invite_status == 200
    assert invite_payload["invite"]["code"] == "invite-code"
    assert gateway.calls == ["get_ai_settings", "update_ai_settings", "create_operator_invite"]


def test_http_rejects_invalid_ticket_action_json() -> None:
    status, payload = request_json(
        gateway=StubGateway(),
        method="POST",
        path=f"/api/tickets/{uuid4()}/notes",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
        body=b"{invalid",
    )

    assert status == 400
    assert payload["code"] == "validation_error"


def test_http_rejects_ticket_action_validation_error() -> None:
    status, payload = request_json(
        gateway=StubGateway(),
        method="POST",
        path=f"/api/tickets/{uuid4()}/notes",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
        body=json.dumps({"text": "   "}).encode(),
    )

    assert status == 400
    assert payload["code"] == "validation_error"


def test_http_serves_static_frontend_assets() -> None:
    status, headers, body = request_raw(
        gateway=StubGateway(),
        path="/",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )
    asset_status, asset_headers, asset_body = request_raw(
        gateway=StubGateway(),
        path="/assets/app.js",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert b"<html" in body.lower()
    assert asset_status == 200
    assert "javascript" in asset_headers["Content-Type"]
    assert asset_body


def request_json(
    *,
    gateway: StubGateway,
    path: str,
    init_data: str,
    method: str = "GET",
    body: bytes = b"",
    init_data_ttl_seconds: int = 3600,
) -> tuple[int, dict[str, Any]]:
    status, _headers, response_body = request_raw(
        gateway=gateway,
        path=path,
        init_data=init_data,
        method=method,
        body=body,
        init_data_ttl_seconds=init_data_ttl_seconds,
    )
    return status, cast(dict[str, Any], json.loads(response_body.decode()))


def request_raw(
    *,
    gateway: StubGateway,
    path: str,
    init_data: str,
    method: str = "GET",
    body: bytes = b"",
    init_data_ttl_seconds: int = 3600,
) -> tuple[int, Any, bytes]:
    app = create_mini_app(
        gateway=cast(Any, gateway),
        config=MiniAppConfig(
            listen_host="127.0.0.1",
            port=0,
            init_data_ttl_seconds=init_data_ttl_seconds,
        ),
        bot_token=BOT_TOKEN,
        static_dir=Path("src/mini_app/static"),
    )
    response = asyncio.run(
        _request_asgi(
            app=app,
            method=method,
            path=path,
            headers={"X-Telegram-Init-Data": init_data},
            content=body,
        )
    )
    return response.status_code, response.headers, response.content


async def _request_asgi(
    *,
    app: Any,
    method: str,
    path: str,
    headers: dict[str, str],
    content: bytes,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://mini-app.test") as client:
        return await client.request(method, path, headers=headers, content=content)


def build_init_data(*, auth_date: datetime) -> str:
    values = {
        "auth_date": str(int(auth_date.timestamp())),
        "query_id": "AAEAAAE",
        "user": json.dumps(
            {
                "id": 1001,
                "first_name": "Анна",
                "last_name": "Смирнова",
                "username": "anna.support",
                "language_code": "ru",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    values["hash"] = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(values)
