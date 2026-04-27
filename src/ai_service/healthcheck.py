from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from ai_service.grpc.client import ping_ai_service
from infrastructure.ai.provider import build_ai_provider
from infrastructure.config.settings import AIConfig, get_settings
from infrastructure.health import (
    EXPECTED_HEALTH_FAILURES,
    ProbeCheck,
    ProbeReport,
    ProbeStatus,
)
from infrastructure.logging import configure_logging


async def run() -> int:
    settings = get_settings()
    configure_logging(settings.logging, app=settings.app)

    provider = build_ai_provider(settings.ai)
    report = ProbeReport(
        checks=(
            ProbeCheck(
                name="bootstrap",
                category="liveness",
                status=ProbeStatus.OK,
                detail="health probe запущен",
                affects_readiness=False,
            ),
            ProbeCheck(
                name="ai_service_auth",
                category="readiness",
                status=(
                    ProbeStatus.OK if settings.ai_service_auth.token.strip() else ProbeStatus.FAIL
                ),
                detail=(
                    "internal ai-service auth настроен"
                    if settings.ai_service_auth.token.strip()
                    else "AI_SERVICE_AUTH__TOKEN не задан"
                ),
            ),
            ProbeCheck(
                name="ai_provider",
                category="operations",
                status=ProbeStatus.OK if provider.is_enabled else ProbeStatus.WARN,
                detail=build_ai_provider_visibility_detail(
                    settings.ai,
                    provider_enabled=provider.is_enabled,
                    model_id=provider.model_id,
                    disabled_reason=getattr(provider, "disabled_reason", None),
                ),
                affects_readiness=False,
            ),
            await _run_probe(
                name="ai_service_grpc",
                category="service",
                detail=f"ai-service gRPC отвечает на {settings.ai_service.target}",
                probe=lambda: ping_ai_service(
                    settings.ai_service,
                    auth_config=settings.ai_service_auth,
                    resilience_config=settings.resilience,
                ),
            ),
        )
    )
    print(report.render())
    return report.exit_code


async def _run_probe(
    *,
    name: str,
    category: str,
    detail: str,
    probe: Callable[[], Awaitable[bool]],
) -> ProbeCheck:
    try:
        ok = await probe()
    except EXPECTED_HEALTH_FAILURES as exc:
        return ProbeCheck(
            name=name,
            category=category,
            status=ProbeStatus.FAIL,
            detail=f"{exc.__class__.__name__}: {exc}",
        )

    if ok:
        return ProbeCheck(
            name=name,
            category=category,
            status=ProbeStatus.OK,
            detail=detail,
        )

    return ProbeCheck(
        name=name,
        category=category,
        status=ProbeStatus.FAIL,
        detail="проверка вернула отрицательный результат",
    )


def build_ai_provider_visibility_detail(
    config: AIConfig,
    *,
    provider_enabled: bool,
    model_id: str | None,
    disabled_reason: str | None = None,
) -> str:
    provider_configured = config.normalized_provider != "disabled" and bool(config.model_id)
    if provider_enabled:
        return (
            f"provider_configured=yes provider={config.normalized_provider} "
            f"model_id={model_id or '<none>'} timeout_seconds={config.timeout_seconds}"
        )
    reason = disabled_reason or "AI provider is disabled."
    return (
        f"provider_configured={'yes' if provider_configured else 'no'} "
        f"provider={config.normalized_provider} model_id={config.model_id or '<none>'} "
        f"status=disabled reason={reason}"
    )


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
