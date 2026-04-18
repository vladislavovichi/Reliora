from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from infrastructure.health import EXPECTED_HEALTH_FAILURES

AsyncDependencyCheck = Callable[[], Awaitable[bool]]


@dataclass(slots=True, frozen=True)
class DiagnosticsCheck:
    name: str
    category: str
    ok: bool
    detail: str
    affects_readiness: bool = True


@dataclass(slots=True, frozen=True)
class DiagnosticsReport:
    checks: tuple[DiagnosticsCheck, ...]

    @property
    def is_healthy(self) -> bool:
        return self.readiness_ok

    @property
    def liveness_ok(self) -> bool:
        return all(check.ok for check in self.checks if check.category == "liveness")

    @property
    def readiness_ok(self) -> bool:
        return all(
            check.ok
            for check in self.checks
            if check.category != "liveness" and check.affects_readiness
        )

    @property
    def has_warnings(self) -> bool:
        return any(not check.ok and not check.affects_readiness for check in self.checks)


@dataclass(slots=True)
class DiagnosticsService:
    database_check: AsyncDependencyCheck
    redis_check: AsyncDependencyCheck
    backend_check: AsyncDependencyCheck
    backend_auth_configured: bool
    dry_run: bool
    bot_configured: bool
    bot_initialized: bool
    dispatcher_initialized: bool
    fsm_storage_initialized: bool
    redis_workflow_initialized: bool
    mini_app_url_valid: bool = False
    mini_app_url_detail: str = "MINI_APP__PUBLIC_URL не задан."
    mini_app_http_check: AsyncDependencyCheck | None = None
    mini_app_http_target: str = ""

    async def collect_report(self) -> DiagnosticsReport:
        checks = [
            DiagnosticsCheck(
                name="bootstrap",
                category="liveness",
                ok=True,
                detail="runtime инициализирован",
            ),
            DiagnosticsCheck(
                name="backend_auth",
                category="readiness",
                ok=self.backend_auth_configured,
                detail=(
                    "internal backend auth настроен"
                    if self.backend_auth_configured
                    else "BACKEND_AUTH__TOKEN не задан"
                ),
            ),
            await self._run_check(
                name="postgresql",
                category="dependency",
                check=self.database_check,
                success_detail="подключение установлено",
            ),
            await self._run_check(
                name="redis",
                category="dependency",
                check=self.redis_check,
                success_detail="подключение установлено",
            ),
            await self._run_check(
                name="backend_grpc",
                category="dependency",
                check=self.backend_check,
                success_detail="внутренний gRPC backend доступен",
            ),
            DiagnosticsCheck(
                name="bot_runtime",
                category="readiness",
                ok=self._is_bot_runtime_ready(),
                detail=self._build_bot_runtime_detail(),
            ),
            DiagnosticsCheck(
                name="mini_app_url",
                category="integration",
                ok=self.mini_app_url_valid,
                detail=self.mini_app_url_detail,
                affects_readiness=False,
            ),
        ]
        if self.mini_app_http_check is not None:
            checks.append(
                await self._run_check(
                    name="mini_app_http",
                    category="integration",
                    check=self.mini_app_http_check,
                    success_detail=f"Mini App endpoint доступен ({self.mini_app_http_target})",
                    affects_readiness=False,
                )
            )
        return DiagnosticsReport(checks=tuple(checks))

    async def _run_check(
        self,
        *,
        name: str,
        category: str,
        check: AsyncDependencyCheck,
        success_detail: str,
        affects_readiness: bool = True,
    ) -> DiagnosticsCheck:
        try:
            is_ready = await check()
        except EXPECTED_HEALTH_FAILURES as exc:
            return DiagnosticsCheck(
                name=name,
                category=category,
                ok=False,
                detail=f"{exc.__class__.__name__}: {exc}",
                affects_readiness=affects_readiness,
            )

        if is_ready:
            return DiagnosticsCheck(
                name=name,
                category=category,
                ok=True,
                detail=success_detail,
                affects_readiness=affects_readiness,
            )

        return DiagnosticsCheck(
            name=name,
            category=category,
            ok=False,
            detail="проверка вернула отрицательный результат",
            affects_readiness=affects_readiness,
        )

    def _is_bot_runtime_ready(self) -> bool:
        if self.dry_run:
            return self.fsm_storage_initialized and self.redis_workflow_initialized

        return (
            self.bot_configured
            and self.bot_initialized
            and self.dispatcher_initialized
            and self.fsm_storage_initialized
            and self.redis_workflow_initialized
        )

    def _build_bot_runtime_detail(self) -> str:
        if self.dry_run:
            if self.fsm_storage_initialized and self.redis_workflow_initialized:
                return "polling отключен из-за APP__DRY_RUN=true"
            return "часть Telegram runtime не инициализирована в dry-run режиме"

        if not self.bot_configured:
            return "BOT__TOKEN не задан"
        if not self.bot_initialized:
            return "экземпляр бота не инициализирован"
        if not self.dispatcher_initialized:
            return "dispatcher не инициализирован"
        if not self.fsm_storage_initialized:
            return "FSM storage не инициализирован"
        if not self.redis_workflow_initialized:
            return "Redis workflow runtime не инициализирован"
        return "Telegram runtime готов"
