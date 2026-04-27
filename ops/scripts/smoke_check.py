from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from ai_service.grpc.client import ping_ai_service
from ai_service.healthcheck import build_ai_provider_visibility_detail
from app.bootstrap import build_runtime as build_app_runtime
from app.bootstrap import close_runtime as close_app_runtime
from app.runtime_factories import build_helpdesk_backend_client_factory
from application.contracts.ai import PredictTicketCategoryCommand
from backend.grpc.client import ping_helpdesk_backend
from infrastructure.ai.provider import build_ai_provider
from infrastructure.config.settings import Settings, get_settings
from infrastructure.db.session import build_engine, dispose_engine, ping_database_engine
from infrastructure.health import ProbeCheck, ProbeReport, ProbeStatus
from infrastructure.logging import configure_logging
from infrastructure.redis.client import build_redis_client, close_redis_client, ping_redis_client


async def run() -> int:
    settings = get_settings()
    configure_logging(settings.logging, app=settings.app)

    db_engine = build_engine(settings.database)
    redis = build_redis_client(settings.redis)
    ai_provider = build_ai_provider(settings.ai)
    checks: list[ProbeCheck] = [
        ProbeCheck(
            name="smoke_runner",
            category="liveness",
            status=ProbeStatus.OK,
            detail="smoke-check запущен",
            affects_readiness=False,
        ),
    ]

    try:
        checks.append(
            await _run_probe(
                name="postgresql",
                category="dependency",
                detail="PostgreSQL доступен",
                probe=lambda: ping_database_engine(db_engine),
            )
        )
        checks.append(
            await _run_probe(
                name="redis",
                category="dependency",
                detail="Redis доступен",
                probe=lambda: ping_redis_client(redis),
            )
        )
        checks.append(
            ProbeCheck(
                name="ai_provider_config",
                category="operations",
                status=ProbeStatus.OK if ai_provider.is_enabled else ProbeStatus.WARN,
                detail=build_ai_provider_visibility_detail(
                    settings.ai,
                    provider_enabled=ai_provider.is_enabled,
                    model_id=ai_provider.model_id,
                    disabled_reason=getattr(ai_provider, "disabled_reason", None),
                ),
                affects_readiness=False,
            )
        )
        checks.append(
            await _run_probe(
                name="ai_service_grpc",
                category="dependency",
                detail=f"ai-service доступен по {settings.ai_service.target}",
                probe=lambda: ping_ai_service(
                    settings.ai_service,
                    auth_config=settings.ai_service_auth,
                    resilience_config=settings.resilience,
                ),
            )
        )
        checks.append(
            await _run_probe(
                name="backend_grpc",
                category="dependency",
                detail=f"backend доступен по {settings.backend_service.target}",
                probe=lambda: ping_helpdesk_backend(
                    settings.backend_service,
                    auth_config=settings.backend_auth,
                    resilience_config=settings.resilience,
                ),
            )
        )
        checks.extend(await _run_backend_functional_smoke(settings))
        checks.append(await _run_bot_smoke(settings))

        report = ProbeReport(checks=tuple(checks))
        print(report.render())
        return report.exit_code
    finally:
        await close_redis_client(redis)
        await dispose_engine(db_engine)


async def _run_backend_functional_smoke(settings: Settings) -> list[ProbeCheck]:
    backend_client_factory = build_helpdesk_backend_client_factory(settings)
    async with backend_client_factory() as client:
        categories = await client.list_client_ticket_categories()
        checks: list[ProbeCheck] = [
            ProbeCheck(
                name="list_client_ticket_categories",
                category="functional",
                status=ProbeStatus.OK,
                detail=f"backend вернул {len(categories)} активных категорий",
            )
        ]

        if not categories:
            checks.append(
                ProbeCheck(
                    name="predict_ticket_category",
                    category="functional",
                    status=ProbeStatus.WARN,
                    detail=(
                        "проверка backend -> ai-service пропущена: активные категории не заведены"
                    ),
                    affects_readiness=False,
                )
            )
            return checks

        prediction = await client.predict_ticket_category(
            PredictTicketCategoryCommand(text="Не могу войти в личный кабинет")
        )
        prediction_detail = (
            f"получена рекомендация темы {prediction.category_code}"
            if prediction.available and prediction.category_code
            else "backend дошёл до AI-контура и вернул корректный ответ без рекомендации"
        )
        checks.append(
            ProbeCheck(
                name="predict_ticket_category",
                category="functional",
                status=ProbeStatus.OK,
                detail=prediction_detail,
            )
        )
        return checks


async def _run_bot_smoke(settings: Settings) -> ProbeCheck:
    runtime = await build_app_runtime(settings)
    try:
        report = await runtime.diagnostics_service.collect_report()
    finally:
        await close_app_runtime(runtime)

    if report.readiness_ok:
        return ProbeCheck(
            name="bot_runtime",
            category="functional",
            status=ProbeStatus.OK,
            detail="bot runtime dependencies готовы",
        )

    failing = next((check for check in report.checks if not check.ok), None)
    detail = failing.detail if failing is not None else "бот не готов по внутренней диагностике"
    return ProbeCheck(
        name="bot_runtime",
        category="functional",
        status=ProbeStatus.FAIL,
        detail=detail,
    )


async def _run_probe(
    *,
    name: str,
    category: str,
    detail: str,
    probe: Callable[[], Awaitable[bool]],
) -> ProbeCheck:
    try:
        ok = await probe()
    except Exception as exc:
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
