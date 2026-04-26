from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import re
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, parse_qs, urlparse
from uuid import UUID

from application.contracts.actors import OperatorIdentity
from application.services.stats import AnalyticsWindow
from application.use_cases.analytics.exports import AnalyticsExportFormat, AnalyticsSection
from application.use_cases.tickets.exports import TicketReportFormat
from domain.enums.roles import UserRole
from infrastructure.config.settings import MiniAppConfig
from mini_app.api import BinaryPayload, MiniAppGateway
from mini_app.auth import (
    TelegramMiniAppAuthError,
    TelegramMiniAppUser,
    validate_telegram_mini_app_init_data,
)
from mini_app.launch import ResolvedMiniAppLaunch, resolve_mini_app_launch

logger = logging.getLogger(__name__)

_TICKET_ROUTE = re.compile(r"^/api/tickets/([0-9a-fA-F-]{36})$")
_TICKET_ACTION_ROUTE = re.compile(
    r"^/api/tickets/([0-9a-fA-F-]{36})/(take|close|escalate|assign|notes)$"
)
_TICKET_AI_SUMMARY_ROUTE = re.compile(r"^/api/tickets/([0-9a-fA-F-]{36})/ai-summary$")
_TICKET_AI_REPLY_DRAFT_ROUTE = re.compile(r"^/api/tickets/([0-9a-fA-F-]{36})/ai-reply-draft$")
_TICKET_MACRO_ROUTE = re.compile(r"^/api/tickets/([0-9a-fA-F-]{36})/macros/(\d+)$")
_TICKET_EXPORT_ROUTE = re.compile(r"^/api/tickets/([0-9a-fA-F-]{36})/export$")


@dataclass(slots=True)
class MiniAppHttpServer:
    config: MiniAppConfig
    bot_token: str
    gateway: MiniAppGateway
    static_dir: Path
    server: ThreadingHTTPServer | None = None

    def build_server(self) -> ThreadingHTTPServer:
        handler_cls = build_handler_class(
            gateway=self.gateway,
            config=self.config,
            bot_token=self.bot_token,
            static_dir=self.static_dir,
        )
        self.server = ThreadingHTTPServer((self.config.listen_host, self.config.port), handler_cls)
        return self.server


def build_handler_class(
    *,
    gateway: MiniAppGateway,
    config: MiniAppConfig,
    bot_token: str,
    static_dir: Path,
) -> type[BaseHTTPRequestHandler]:
    gateway_ref = gateway
    config_ref = config
    bot_token_ref = bot_token
    static_dir_ref = static_dir

    class MiniAppRequestHandler(BaseHTTPRequestHandler):
        gateway = gateway_ref
        config = config_ref
        bot_token = bot_token_ref
        static_dir = static_dir_ref

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

        def log_message(self, format: str, *args: object) -> None:
            logger.info("mini-app http %s - %s", self.address_string(), format % args)

        def _dispatch(self, method: str) -> None:
            parsed = urlparse(self.path)
            path = parsed.path

            try:
                if self._handle_public_request(method=method, path=path, parsed=parsed):
                    return
                if not path.startswith("/api/"):
                    self._write_json(HTTPStatus.NOT_FOUND, {"error": "Маршрут Mini App не найден."})
                    return

                launch, user, session = self._load_session()
                self._handle_authenticated_request(
                    method=method,
                    path=path,
                    parsed=parsed,
                    launch=launch,
                    user=user,
                    session=session,
                )
            except TelegramMiniAppAuthError as exc:
                logger.warning(
                    (
                        "Mini App auth failed method=%s path=%s code=%s source=%s "
                        "client_source=%s telegram_webapp=%s telegram_user=%s "
                        "attempted_sources=%s diagnostics=%s"
                    ),
                    method,
                    path,
                    exc.code,
                    getattr(self, "_request_launch_source", "<unresolved>"),
                    getattr(self, "_request_client_source", "<unknown>"),
                    getattr(self, "_request_telegram_webapp", "<unknown>"),
                    getattr(self, "_request_telegram_user", "<unknown>"),
                    getattr(self, "_request_attempted_sources", "<none>"),
                    getattr(self, "_request_launch_diagnostics", "<none>"),
                )
                self._write_json(
                    HTTPStatus.UNAUTHORIZED,
                    {
                        "error": str(exc),
                        "code": exc.code,
                    },
                )
            except PermissionError as exc:
                self._write_json(
                    HTTPStatus.FORBIDDEN,
                    {"error": str(exc), "code": "access_denied"},
                )
            except LookupError as exc:
                self._write_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": str(exc), "code": "not_found"},
                )
            except ValueError as exc:
                self._write_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": str(exc), "code": "invalid_request"},
                )
            except (ConnectionError, OSError, RuntimeError, TimeoutError) as exc:
                logger.warning(
                    "Mini App backend dependency failed method=%s path=%s error=%s",
                    method,
                    path,
                    exc,
                )
                self._write_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "error": "Mini App временно недоступен. Попробуйте ещё раз чуть позже.",
                        "code": "backend_unavailable",
                    },
                )
            except Exception:  # noqa: BLE001
                logger.exception("Mini App request failed method=%s path=%s", method, self.path)
                self._write_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {
                        "error": "Mini App временно недоступен. Попробуйте ещё раз.",
                        "code": "internal_error",
                    },
                )

        def _handle_public_request(
            self,
            *,
            method: str,
            path: str,
            parsed: ParseResult,
        ) -> bool:
            del parsed
            if method == "GET" and path == "/healthz":
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "mini_app": {
                            "public_url": self.config.public_url or None,
                            "public_url_valid": self.config.public_url_is_valid,
                            "detail": self.config.public_url_status_detail,
                        },
                    },
                )
                return True
            if method == "GET" and (path == "/" or path == "/index.html"):
                self._serve_file(
                    self.static_dir / "index.html",
                    content_type="text/html; charset=utf-8",
                )
                return True
            if method == "GET" and path.startswith("/assets/"):
                asset_path = path.removeprefix("/assets/")
                self._serve_file(self.static_dir / "assets" / asset_path)
                return True
            return False

        def _handle_authenticated_request(
            self,
            *,
            method: str,
            path: str,
            parsed: ParseResult,
            launch: ResolvedMiniAppLaunch,
            user: TelegramMiniAppUser,
            session: dict[str, Any],
        ) -> None:
            if method == "GET" and path == "/api/session":
                self._write_json(
                    HTTPStatus.OK,
                    {
                        **session,
                        "launch": {
                            "source": launch.source,
                            "client_source": launch.client_source,
                        },
                    },
                )
                return

            if session["access"]["role"] == UserRole.USER.value:
                self._write_json(
                    HTTPStatus.FORBIDDEN,
                    {"error": ("Рабочее место доступно только операторам и суперадминистраторам.")},
                )
                return

            if method == "GET" and path == "/api/dashboard":
                self._write_async_json(self.gateway.get_dashboard(user=user))
                return
            if method == "GET" and path == "/api/queue":
                self._write_async_json(self.gateway.list_queue(user=user))
                return
            if method == "POST" and path == "/api/queue/take-next":
                self._write_async_json(self.gateway.take_next_ticket(user=user))
                return
            if method == "GET" and path == "/api/my-tickets":
                self._write_async_json(self.gateway.list_my_tickets(user=user))
                return
            if method == "GET" and path == "/api/archive":
                self._write_async_json(self.gateway.list_archive(user=user))
                return
            if method == "GET" and path == "/api/analytics":
                window = self._parse_analytics_window(parsed)
                self._write_async_json(self.gateway.get_analytics(user=user, window=window))
                return
            if method == "GET" and path == "/api/analytics/export":
                self._handle_analytics_export(user=user, parsed=parsed)
                return
            if method == "GET" and path == "/api/admin/operators":
                self._require_admin(session)
                self._write_async_json(self.gateway.list_operators(user=user))
                return
            if method == "POST" and path == "/api/admin/invites":
                self._require_admin(session)
                self._write_async_json(self.gateway.create_operator_invite(user=user))
                return
            if self._handle_ticket_routes(method=method, path=path, parsed=parsed, user=user):
                return

            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Маршрут Mini App не найден."})

        def _handle_analytics_export(
            self,
            *,
            user: TelegramMiniAppUser,
            parsed: ParseResult,
        ) -> None:
            window = self._parse_analytics_window(parsed)
            query = parse_qs(parsed.query)
            section = AnalyticsSection(query.get("section", ["overview"])[0])
            analytics_format = AnalyticsExportFormat(query.get("format", ["html"])[0])
            self._write_binary(
                asyncio.run(
                    self.gateway.export_analytics(
                        user=user,
                        window=window,
                        section=section,
                        format=analytics_format,
                    )
                )
            )

        def _handle_ticket_routes(
            self,
            *,
            method: str,
            path: str,
            parsed: ParseResult,
            user: TelegramMiniAppUser,
        ) -> bool:
            ticket_match = _TICKET_ROUTE.fullmatch(path)
            if method == "GET" and ticket_match is not None:
                ticket_public_id = UUID(ticket_match.group(1))
                self._write_async_json(
                    self.gateway.get_ticket_workspace(
                        user=user,
                        ticket_public_id=ticket_public_id,
                    )
                )
                return True

            action_match = _TICKET_ACTION_ROUTE.fullmatch(path)
            if method == "POST" and action_match is not None:
                return self._handle_ticket_action(
                    user=user,
                    ticket_public_id=UUID(action_match.group(1)),
                    action=action_match.group(2),
                )

            ai_summary_match = _TICKET_AI_SUMMARY_ROUTE.fullmatch(path)
            if method == "POST" and ai_summary_match is not None:
                self._write_async_json(
                    self.gateway.refresh_ticket_ai_summary(
                        user=user,
                        ticket_public_id=UUID(ai_summary_match.group(1)),
                    )
                )
                return True

            ai_reply_draft_match = _TICKET_AI_REPLY_DRAFT_ROUTE.fullmatch(path)
            if method == "POST" and ai_reply_draft_match is not None:
                self._write_async_json(
                    self.gateway.generate_ticket_reply_draft(
                        user=user,
                        ticket_public_id=UUID(ai_reply_draft_match.group(1)),
                    )
                )
                return True

            macro_match = _TICKET_MACRO_ROUTE.fullmatch(path)
            if method == "POST" and macro_match is not None:
                self._write_async_json(
                    self.gateway.apply_macro(
                        user=user,
                        ticket_public_id=UUID(macro_match.group(1)),
                        macro_id=int(macro_match.group(2)),
                    )
                )
                return True

            export_match = _TICKET_EXPORT_ROUTE.fullmatch(path)
            if method == "GET" and export_match is not None:
                query = parse_qs(parsed.query)
                ticket_format = TicketReportFormat(query.get("format", ["html"])[0])
                self._write_binary(
                    asyncio.run(
                        self.gateway.export_ticket(
                            user=user,
                            ticket_public_id=UUID(export_match.group(1)),
                            format=ticket_format,
                        )
                    )
                )
                return True

            return False

        def _handle_ticket_action(
            self,
            *,
            user: TelegramMiniAppUser,
            ticket_public_id: UUID,
            action: str,
        ) -> bool:
            if action == "take":
                self._write_async_json(
                    self.gateway.take_ticket(
                        user=user,
                        ticket_public_id=ticket_public_id,
                    )
                )
                return True
            if action == "close":
                self._write_async_json(
                    self.gateway.close_ticket(
                        user=user,
                        ticket_public_id=ticket_public_id,
                    )
                )
                return True
            if action == "escalate":
                self._write_async_json(
                    self.gateway.escalate_ticket(
                        user=user,
                        ticket_public_id=ticket_public_id,
                    )
                )
                return True

            payload = self._read_json_body()
            if action == "assign":
                operator = OperatorIdentity(
                    telegram_user_id=_require_int(payload, "telegram_user_id"),
                    display_name=_require_string(payload, "display_name"),
                    username=_optional_string(payload, "username"),
                )
                self._write_async_json(
                    self.gateway.assign_ticket(
                        user=user,
                        ticket_public_id=ticket_public_id,
                        operator_identity=operator,
                    )
                )
                return True
            if action == "notes":
                self._write_async_json(
                    self.gateway.add_note(
                        user=user,
                        ticket_public_id=ticket_public_id,
                        text=_require_string(payload, "text"),
                    )
                )
                return True
            return False

        def _load_session(
            self,
        ) -> tuple[ResolvedMiniAppLaunch, TelegramMiniAppUser, dict[str, Any]]:
            launch = self._resolve_launch()
            validated = validate_telegram_mini_app_init_data(
                init_data=launch.init_data,
                bot_token=self.bot_token,
                max_age_seconds=self.config.init_data_ttl_seconds,
            )
            session = asyncio.run(self.gateway.get_session(user=validated.user))
            return launch, validated.user, session

        def _resolve_launch(self) -> ResolvedMiniAppLaunch:
            launch = resolve_mini_app_launch(path=self.path, headers=dict(self.headers.items()))
            self._request_launch_source = launch.source
            self._request_client_source = launch.client_source or "<unknown>"
            self._request_telegram_webapp = _format_presence(launch.is_telegram_webapp)
            self._request_telegram_user = _format_presence(launch.has_telegram_user)
            self._request_attempted_sources = ",".join(launch.attempted_sources) or "<none>"
            self._request_launch_diagnostics = ",".join(launch.diagnostics) or "<none>"
            if launch.has_init_data:
                logger.debug(
                    (
                        "Mini App launch resolved source=%s client_source=%s path=%s "
                        "telegram_webapp=%s telegram_user=%s platform=%s version=%s "
                        "attempted_sources=%s diagnostics=%s"
                    ),
                    launch.source,
                    launch.client_source or "<unknown>",
                    urlparse(self.path).path,
                    _format_presence(launch.is_telegram_webapp),
                    _format_presence(launch.has_telegram_user),
                    launch.client_platform or "<unknown>",
                    launch.client_version or "<unknown>",
                    ",".join(launch.attempted_sources) or "<none>",
                    ",".join(launch.diagnostics) or "<none>",
                )
                return launch

            logger.warning(
                (
                    "Mini App launch missing source=%s client_source=%s path=%s "
                    "telegram_webapp=%s telegram_user=%s platform=%s version=%s "
                    "attempted_sources=%s diagnostics=%s"
                ),
                launch.source,
                launch.client_source or "<unknown>",
                urlparse(self.path).path,
                _format_presence(launch.is_telegram_webapp),
                _format_presence(launch.has_telegram_user),
                launch.client_platform or "<unknown>",
                launch.client_version or "<unknown>",
                ",".join(launch.attempted_sources) or "<none>",
                ",".join(launch.diagnostics) or "<none>",
            )
            return launch

        def _parse_analytics_window(self, parsed: ParseResult) -> AnalyticsWindow:
            query = parse_qs(parsed.query)
            return AnalyticsWindow(query.get("window", ["7d"])[0])

        def _require_admin(self, session: dict[str, Any]) -> None:
            if session["access"]["role"] != UserRole.SUPER_ADMIN.value:
                raise PermissionError("Доступно только суперадминистраторам.")

        def _read_json_body(self) -> dict[str, Any]:
            content_length = int(self.headers.get("Content-Length", "0") or "0")
            payload = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                decoded = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Не удалось разобрать JSON payload.") from exc
            if not isinstance(decoded, dict):
                raise ValueError("JSON payload должен быть объектом.")
            return decoded

        def _write_async_json(self, awaitable: Any) -> None:
            result = asyncio.run(awaitable)
            self._write_json(HTTPStatus.OK, result)

        def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _write_binary(self, payload: BinaryPayload) -> None:
            self.send_response(HTTPStatus.OK.value)
            self.send_header("Content-Type", payload.content_type)
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{payload.filename}"',
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload.content)))
            self.end_headers()
            self.wfile.write(payload.content)

        def _serve_file(self, path: Path, *, content_type: str | None = None) -> None:
            resolved_base = self.static_dir.resolve()
            resolved_path = path.resolve()
            if resolved_base not in resolved_path.parents and resolved_path != resolved_base:
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "Файл Mini App не найден."})
                return
            if not resolved_path.is_file():
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "Файл Mini App не найден."})
                return

            payload = resolved_path.read_bytes()
            guessed_type = content_type or mimetypes.guess_type(resolved_path.name)[0]
            self.send_response(HTTPStatus.OK.value)
            self.send_header(
                "Content-Type",
                guessed_type or "application/octet-stream",
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return MiniAppRequestHandler


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Поле {key} должно быть строкой.")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"Поле {key} не должно быть пустым.")
    return normalized


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Поле {key} должно быть строкой.")
    normalized = value.strip()
    return normalized or None


def _require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"Поле {key} должно быть числом.")
    return value


def _format_presence(value: bool | None) -> str:
    if value is True:
        return "present"
    if value is False:
        return "missing"
    return "unknown"
