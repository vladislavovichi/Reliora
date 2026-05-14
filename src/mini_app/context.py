from __future__ import annotations

# ruff: noqa: B008
import logging
from dataclasses import dataclass
from typing import Any, cast

from fastapi import Depends
from starlette.requests import Request

from application.errors import ForbiddenError
from domain.enums.roles import UserRole
from infrastructure.config.settings import MiniAppConfig
from mini_app.api import MiniAppGateway
from mini_app.auth import (
    TelegramMiniAppUser,
    validate_telegram_mini_app_init_data,
)
from mini_app.launch import ResolvedMiniAppLaunch, resolve_mini_app_launch

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class MiniAppHttpDependencies:
    gateway: MiniAppGateway
    config: MiniAppConfig
    bot_token: str


@dataclass(slots=True, frozen=True)
class MiniAppAuthenticatedContext:
    launch: ResolvedMiniAppLaunch
    user: TelegramMiniAppUser
    session: dict[str, Any]
    gateway: MiniAppGateway


def get_mini_app_dependencies(request: Request) -> MiniAppHttpDependencies:
    return cast(MiniAppHttpDependencies, request.app.state.mini_app_dependencies)


async def load_mini_app_session(
    request: Request,
) -> MiniAppAuthenticatedContext:
    deps = get_mini_app_dependencies(request)
    request_path = _request_path_with_query(request)
    launch = resolve_mini_app_launch(path=request_path, headers=request.headers)
    _store_launch_diagnostics(request, launch)
    _log_launch_resolution(path=request_path, launch=launch)
    validated = validate_telegram_mini_app_init_data(
        init_data=launch.init_data,
        bot_token=deps.bot_token,
        max_age_seconds=deps.config.init_data_ttl_seconds,
    )
    session = await deps.gateway.get_session(user=validated.user)
    return MiniAppAuthenticatedContext(
        launch=launch,
        user=validated.user,
        session=session,
        gateway=deps.gateway,
    )


async def require_operator_context(
    request: Request,
    context: MiniAppAuthenticatedContext = Depends(load_mini_app_session),
) -> MiniAppAuthenticatedContext:
    del request
    if context.session["access"]["role"] == UserRole.USER.value:
        raise ForbiddenError("Рабочее место доступно только операторам и суперадминистраторам.")
    return context


def _request_path_with_query(request: Request) -> str:
    if request.url.query:
        return f"{request.url.path}?{request.url.query}"
    return request.url.path


def _store_launch_diagnostics(request: Request, launch: ResolvedMiniAppLaunch) -> None:
    request.state.mini_app_launch_source = launch.source
    request.state.mini_app_client_source = launch.client_source or "<unknown>"
    request.state.mini_app_telegram_webapp = _format_presence(launch.is_telegram_webapp)
    request.state.mini_app_telegram_user = _format_presence(launch.has_telegram_user)
    request.state.mini_app_attempted_sources = ",".join(launch.attempted_sources) or "<none>"
    request.state.mini_app_launch_diagnostics = ",".join(launch.diagnostics) or "<none>"


def log_auth_failure(
    request: Request,
    *,
    code: str,
) -> None:
    logger.warning(
        (
            "Mini App auth failed method=%s path=%s code=%s source=%s "
            "client_source=%s telegram_webapp=%s telegram_user=%s "
            "attempted_sources=%s diagnostics=%s"
        ),
        request.method,
        request.url.path,
        code,
        getattr(request.state, "mini_app_launch_source", "<unresolved>"),
        getattr(request.state, "mini_app_client_source", "<unknown>"),
        getattr(request.state, "mini_app_telegram_webapp", "<unknown>"),
        getattr(request.state, "mini_app_telegram_user", "<unknown>"),
        getattr(request.state, "mini_app_attempted_sources", "<none>"),
        getattr(request.state, "mini_app_launch_diagnostics", "<none>"),
    )


def _log_launch_resolution(*, path: str, launch: ResolvedMiniAppLaunch) -> None:
    log = logger.debug if launch.has_init_data else logger.warning
    state = "resolved" if launch.has_init_data else "missing"
    log(
        (
            "Mini App launch %s source=%s client_source=%s path=%s "
            "telegram_webapp=%s telegram_user=%s platform=%s version=%s "
            "attempted_sources=%s diagnostics=%s"
        ),
        state,
        launch.source,
        launch.client_source or "<unknown>",
        path.split("?", 1)[0],
        _format_presence(launch.is_telegram_webapp),
        _format_presence(launch.has_telegram_user),
        launch.client_platform or "<unknown>",
        launch.client_version or "<unknown>",
        ",".join(launch.attempted_sources) or "<none>",
        ",".join(launch.diagnostics) or "<none>",
    )


def _format_presence(value: bool | None) -> str:
    if value is True:
        return "present"
    if value is False:
        return "missing"
    return "unknown"
