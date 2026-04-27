from __future__ import annotations

from ai_service.healthcheck import build_ai_provider_visibility_detail
from infrastructure.config.settings import AIConfig
from infrastructure.health import ProbeCheck, ProbeReport, ProbeStatus


def test_probe_report_marks_warnings_as_degraded_without_failing_readiness() -> None:
    report = ProbeReport(
        checks=(
            ProbeCheck(
                name="bootstrap",
                category="liveness",
                status=ProbeStatus.OK,
                detail="ok",
                affects_readiness=False,
            ),
            ProbeCheck(
                name="ai_provider",
                category="operations",
                status=ProbeStatus.WARN,
                detail="disabled",
                affects_readiness=False,
            ),
            ProbeCheck(
                name="backend_grpc",
                category="service",
                status=ProbeStatus.OK,
                detail="reachable",
            ),
        )
    )

    assert report.readiness_ok is True
    assert report.has_warnings is True
    assert report.summary == "DEGRADED"
    assert report.exit_code == 0


def test_probe_report_fails_when_readiness_check_fails() -> None:
    report = ProbeReport(
        checks=(
            ProbeCheck(
                name="bootstrap",
                category="liveness",
                status=ProbeStatus.OK,
                detail="ok",
                affects_readiness=False,
            ),
            ProbeCheck(
                name="redis",
                category="dependency",
                status=ProbeStatus.FAIL,
                detail="timeout",
            ),
        )
    )

    assert report.readiness_ok is False
    assert report.summary == "FAIL"
    assert report.exit_code == 1


def test_ai_health_visibility_does_not_expose_secrets() -> None:
    config = AIConfig(
        provider="huggingface",
        model_id="safe-model",
        api_token="hf_secret_token",
        timeout_seconds=3.5,
    )

    detail = build_ai_provider_visibility_detail(
        config,
        provider_enabled=True,
        model_id="safe-model",
    )

    assert "provider_configured=yes" in detail
    assert "safe-model" in detail
    assert "hf_secret_token" not in detail
