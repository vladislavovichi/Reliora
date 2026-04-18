from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from ai_service.grpc.client import ping_ai_service
from backend.grpc.client import ping_helpdesk_backend
from infrastructure.config.settings import get_settings
from infrastructure.db.session import build_engine, dispose_engine, ping_database_engine
from infrastructure.health import (
    EXPECTED_HEALTH_FAILURES,
    ProbeCheck,
    ProbeReport,
    ProbeStatus,
)
from infrastructure.logging import configure_logging
from infrastructure.redis.client import build_redis_client, close_redis_client, ping_redis_client


async def run() -> int:
    settings = get_settings()
    configure_logging(settings.logging, app=settings.app)

    db_engine = build_engine(settings.database)
    redis = build_redis_client(settings.redis)
    try:
        checks = [
            ProbeCheck(
                name="bootstrap",
                category="liveness",
                status=ProbeStatus.OK,
                detail="health probe запущен",
                affects_readiness=False,
            ),
            ProbeCheck(
                name="backend_auth",
                category="readiness",
                status=(
                    ProbeStatus.OK if settings.backend_auth.token.strip() else ProbeStatus.FAIL
                ),
                detail=(
                    "internal backend auth настроен"
                    if settings.backend_auth.token.strip()
                    else "BACKEND_AUTH__TOKEN не задан"
                ),
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
            await _run_probe(
                name="postgresql",
                category="dependency",
                detail="подключение установлено",
                probe=lambda: ping_database_engine(db_engine),
            ),
            await _run_probe(
                name="redis",
                category="dependency",
                detail="подключение установлено",
                probe=lambda: ping_redis_client(redis),
            ),
            await _run_probe(
                name="ai_service_grpc",
                category="dependency",
                detail=f"ai-service доступен по {settings.ai_service.target}",
                probe=lambda: ping_ai_service(
                    settings.ai_service,
                    auth_config=settings.ai_service_auth,
                    resilience_config=settings.resilience,
                ),
            ),
            await _run_probe(
                name="backend_grpc",
                category="service",
                detail=f"backend gRPC отвечает на {settings.backend_service.target}",
                probe=lambda: ping_helpdesk_backend(
                    settings.backend_service,
                    auth_config=settings.backend_auth,
                    resilience_config=settings.resilience,
                ),
            ),
        ]
        report = ProbeReport(checks=tuple(checks))
        print(report.render())
        return report.exit_code
    finally:
        await close_redis_client(redis)
        await dispose_engine(db_engine)


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
