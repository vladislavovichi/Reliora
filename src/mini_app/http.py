from __future__ import annotations

# ruff: noqa: B008
import logging
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

import time

import uvicorn
from fastapi import Depends, FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from application.errors import ApplicationError
from infrastructure.config.settings import MiniAppConfig
from infrastructure.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS, metrics_text
from mini_app.api import MiniAppGateway
from mini_app.auth import TelegramMiniAppAuthError
from mini_app.context import (
    MiniAppAuthenticatedContext,
    MiniAppHttpDependencies,
    log_auth_failure,
    require_operator_context,
)
from mini_app.http_errors import mini_app_error_response
from mini_app.request_parsing import MiniAppRouteNotFound
from mini_app.responses import json_response, static_file_response
from mini_app.routes.admin import build_admin_router
from mini_app.routes.ai import is_ai_route
from mini_app.routes.analytics import build_analytics_router
from mini_app.routes.dashboard import build_dashboard_router
from mini_app.routes.queue import build_queue_router
from mini_app.routes.session import build_session_router
from mini_app.routes.tickets import build_ticket_router

_MAX_REQUEST_BODY_BYTES = 1 * 1024 * 1024  # 1 MB

logger = logging.getLogger(__name__)


def create_mini_app(
    *,
    gateway: MiniAppGateway,
    config: MiniAppConfig,
    bot_token: str,
    static_dir: Path,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.mini_app_dependencies = MiniAppHttpDependencies(
        gateway=gateway,
        config=config,
        bot_token=bot_token,
    )
    app.state.mini_app_static_dir = static_dir

    app.add_middleware(BaseHTTPMiddleware, dispatch=_security_headers_middleware)
    app.add_middleware(BaseHTTPMiddleware, dispatch=_metrics_middleware)
    app.add_middleware(BaseHTTPMiddleware, dispatch=_limit_request_body_middleware)
    _register_exception_handlers(app)
    _register_public_routes(app)
    app.include_router(build_session_router())
    app.include_router(build_dashboard_router())
    app.include_router(build_queue_router())
    app.include_router(build_admin_router())
    app.include_router(build_ticket_router())
    app.include_router(build_analytics_router())
    _register_route_fallback(app)
    return app


@dataclass(slots=True)
class MiniAppHttpServer:
    config: MiniAppConfig
    bot_token: str
    gateway: MiniAppGateway
    static_dir: Path
    app: FastAPI | None = None

    def build_app(self) -> FastAPI:
        self.app = create_mini_app(
            gateway=self.gateway,
            config=self.config,
            bot_token=self.bot_token,
            static_dir=self.static_dir,
        )
        return self.app

    def build_server(self) -> MiniAppUvicornServer:
        return MiniAppUvicornServer(
            app=self.build_app(),
            host=self.config.listen_host,
            port=self.config.port,
        )

    def run(self) -> None:
        self.build_server().serve_forever()


@dataclass(slots=True)
class MiniAppUvicornServer:
    app: FastAPI
    host: str
    port: int

    def serve_forever(self) -> None:
        uvicorn.run(self.app, host=self.host, port=self.port)

    def server_close(self) -> None:
        return None


def _register_public_routes(app: FastAPI) -> None:
    @app.get("/healthz")
    async def healthz(request: Request) -> Response:
        deps: MiniAppHttpDependencies = request.app.state.mini_app_dependencies
        return json_response(
            {
                "status": "ok",
                "mini_app": {
                    "public_url": deps.config.public_url or None,
                    "public_url_valid": deps.config.public_url_is_valid,
                    "detail": deps.config.public_url_status_detail,
                },
            }
        )

    @app.get("/metrics")
    async def prometheus_metrics() -> Response:
        return Response(
            content=metrics_text(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.get("/")
    @app.get("/index.html")
    async def index(request: Request) -> Response:
        static_dir: Path = request.app.state.mini_app_static_dir
        return static_file_response(
            static_dir / "index.html",
            static_dir=static_dir,
            content_type="text/html; charset=utf-8",
        )

    @app.get("/assets/{asset_path:path}")
    async def asset(asset_path: str, request: Request) -> Response:
        static_dir: Path = request.app.state.mini_app_static_dir
        return static_file_response(static_dir / "assets" / asset_path, static_dir=static_dir)


def _register_route_fallback(app: FastAPI) -> None:
    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT"])
    async def api_not_found(
        path: str,
        context: MiniAppAuthenticatedContext = Depends(require_operator_context),
    ) -> Response:
        del path, context
        return _route_not_found_response()

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT"])
    async def not_found(path: str) -> Response:
        del path
        return _route_not_found_response()


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TelegramMiniAppAuthError)
    async def telegram_auth_error(request: Request, exc: TelegramMiniAppAuthError) -> Response:
        log_auth_failure(request, code=exc.code)
        return json_response(
            {
                "error": str(exc),
                "code": "unauthorized" if is_ai_route(request.url.path) else exc.code,
            },
            status_code=HTTPStatus.UNAUTHORIZED,
        )

    @app.exception_handler(ApplicationError)
    async def application_error(request: Request, exc: ApplicationError) -> Response:
        status, payload = mini_app_error_response(exc, is_ai_route=is_ai_route(request.url.path))
        return json_response(payload, status_code=status)

    @app.exception_handler(MiniAppRouteNotFound)
    async def mini_app_route_not_found(request: Request, exc: MiniAppRouteNotFound) -> Response:
        del request, exc
        return _route_not_found_response()

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        del request
        if exc.status_code in {HTTPStatus.NOT_FOUND, HTTPStatus.METHOD_NOT_ALLOWED}:
            return _route_not_found_response()
        return json_response(
            {
                "error": "Mini App временно недоступен. Попробуйте ещё раз.",
                "code": "internal_error",
            },
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> Response:
        if isinstance(exc, ConnectionError | OSError | RuntimeError | TimeoutError):
            logger.warning(
                "Mini App backend dependency failed method=%s path=%s error=%s",
                request.method,
                request.url.path,
                exc,
            )
        else:
            logger.exception(
                "Mini App request failed method=%s path=%s",
                request.method,
                request.url.path,
            )
        status, payload = mini_app_error_response(exc, is_ai_route=is_ai_route(request.url.path))
        return json_response(payload, status_code=status)


async def _metrics_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    response: Response = await call_next(request)
    duration = time.perf_counter() - start
    path_template = request.scope.get("route", None)
    label = path_template.path if path_template is not None else request.url.path
    status = str(response.status_code)
    HTTP_REQUEST_DURATION.labels(
        method=request.method, path_template=label, status_code=status
    ).observe(duration)
    HTTP_REQUESTS.labels(
        method=request.method, path_template=label, status_code=status
    ).inc()
    return response


async def _limit_request_body_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > _MAX_REQUEST_BODY_BYTES:
        return json_response(
            {"error": "Тело запроса слишком большое.", "code": "payload_too_large"},
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        )
    return await call_next(request)


async def _security_headers_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


def _route_not_found_response() -> Response:
    return json_response(
        {"error": "Маршрут Mini App не найден."},
        status_code=HTTPStatus.NOT_FOUND,
    )
