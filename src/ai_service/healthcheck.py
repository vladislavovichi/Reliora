from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from ai_service.grpc.client import ping_ai_service
from infrastructure.ai.provider import build_ai_provider
from infrastructure.config.settings import get_settings
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
                detail=(
                    f"{settings.ai.normalized_provider}:{provider.model_id}"
                    if provider.is_enabled
                    else getattr(provider, "disabled_reason", "AI provider is disabled.")
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


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
