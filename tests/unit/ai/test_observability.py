from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from _pytest.logging import LogCaptureFixture

from ai_service.service import AIApplicationService
from application.contracts.ai import GenerateTicketSummaryCommand
from domain.enums.tickets import TicketStatus
from infrastructure.config.settings import AIConfig
from tests.unit.ai.fakes import FakeAIProvider


async def test_ai_operation_logs_provider_failure_category(caplog: LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="ai_service.service")
    service = AIApplicationService(
        provider=FakeAIProvider(raise_error=True, model_id="ops-model"),
        config=AIConfig(),
    )

    result = await service.generate_ticket_summary(_summary_command(subject="login failure"))

    record = _last_ai_operation_record(caplog.records)
    assert result.available is False
    assert _record_value(record, "operation") == "summary"
    assert _record_value(record, "model_id") == "ops-model"
    assert _record_value(record, "success") is False
    assert _record_value(record, "failure_reason") == "provider_unavailable"
    assert _record_value(record, "retry_count") == 0
    assert isinstance(_record_value(record, "latency_ms"), float)


async def test_invalid_json_logs_invalid_json_without_prompt_or_raw_response(
    caplog: LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="ai_service.service")
    service = AIApplicationService(
        provider=FakeAIProvider(("not json", "still not json"), model_id="ops-model"),
        config=AIConfig(),
    )

    await service.generate_ticket_summary(_summary_command(subject="SECRET CUSTOMER TEXT"))

    record = _last_ai_operation_record(caplog.records)
    assert _record_value(record, "failure_reason") == "invalid_json"
    assert _record_value(record, "retry_count") == 1
    assert "SECRET CUSTOMER TEXT" not in caplog.text
    assert "still not json" not in caplog.text


async def test_validation_failure_logs_validation_failed(caplog: LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="ai_service.service")
    service = AIApplicationService(
        provider=FakeAIProvider(
            (
                '{"short_summary":"Подходит","user_goal":"Подходит",'
                '"actions_taken":"Подходит","current_status":"Подходит"}',
            ),
            model_id="ops-model",
        ),
        config=AIConfig(),
    )

    await service.generate_ticket_summary(_summary_command(subject="login failure"))

    record = _last_ai_operation_record(caplog.records)
    assert _record_value(record, "failure_reason") == "validation_failed"
    assert _record_value(record, "retry_count") == 0


def _summary_command(*, subject: str) -> GenerateTicketSummaryCommand:
    return GenerateTicketSummaryCommand(
        ticket_public_id=uuid4(),
        subject=subject,
        status=TicketStatus.ASSIGNED,
        category_title=None,
    )


def _last_ai_operation_record(records: list[logging.LogRecord]) -> logging.LogRecord:
    return next(
        record
        for record in reversed(records)
        if record.name == "ai_service.service" and record.getMessage() == "AI operation finished"
    )


def _record_value(record: logging.LogRecord, key: str) -> Any:
    return getattr(record, key)
