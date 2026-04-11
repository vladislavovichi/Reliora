from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from pytest import MonkeyPatch

from application.services.stats import (
    AnalyticsCategorySnapshot,
    AnalyticsOperatorSnapshot,
    AnalyticsRatingBucket,
    AnalyticsWindow,
    HelpdeskAnalyticsSnapshot,
    OperatorTicketLoad,
)
from application.use_cases.analytics.exports import AnalyticsSection
from application.use_cases.tickets.exports import (
    TicketReport,
    TicketReportAttachment,
    TicketReportMessage,
)
from domain.enums.tickets import (
    TicketAttachmentKind,
    TicketMessageSenderType,
    TicketStatus,
)
from infrastructure.exports.analytics_snapshot_html import render_analytics_snapshot_html
from infrastructure.exports.ticket_report_csv import render_ticket_report_csv
from infrastructure.exports.ticket_report_html import render_ticket_report_html


def test_render_ticket_report_html_embeds_local_photo(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    photo_dir = tmp_path / "photo"
    photo_dir.mkdir(parents=True, exist_ok=True)
    photo_path = photo_dir / "unique-photo.png"
    photo_path.write_bytes(
        bytes.fromhex(
            "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
            "0000000D49444154789C6360000002000154A24F5D0000000049454E44AE426082"
        )
    )
    monkeypatch.setattr(
        "infrastructure.exports.ticket_report_html.get_settings",
        lambda: SimpleNamespace(assets=SimpleNamespace(path=tmp_path)),
    )

    report = TicketReport(
        public_id=uuid4(),
        public_number="HD-ARCH0001",
        client_chat_id=2002,
        status=TicketStatus.CLOSED,
        priority="high",
        subject="Проверка фото во внутреннем отчёте",
        assigned_operator_id=7,
        assigned_operator_name="Иван Петров",
        assigned_operator_telegram_user_id=1001,
        assigned_operator_username="ivan_petrov",
        created_at=datetime(2026, 4, 7, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 7, 13, 0, tzinfo=UTC),
        first_response_at=datetime(2026, 4, 7, 12, 10, tzinfo=UTC),
        first_response_seconds=600,
        closed_at=datetime(2026, 4, 7, 14, 0, tzinfo=UTC),
        category_code="access",
        category_title="Доступ и вход",
        tags=("vip",),
        feedback=None,
        messages=(
            TicketReportMessage(
                sender_type=TicketMessageSenderType.CLIENT,
                sender_operator_name=None,
                text="Скриншот ошибки во вложении",
                created_at=datetime(2026, 4, 7, 12, 1, tzinfo=UTC),
                attachment=TicketReportAttachment(
                    kind=TicketAttachmentKind.PHOTO,
                    telegram_file_id="file-1",
                    telegram_file_unique_id="unique-photo",
                    filename="screen.png",
                    mime_type="image/png",
                    storage_path="photo/unique-photo.png",
                ),
            ),
        ),
        events=(),
    )

    html = render_ticket_report_html(report).decode("utf-8")

    assert "Материалы дела" in html
    assert "data:image/png;base64," in html
    assert "Скриншот ошибки во вложении" in html
    assert "https://t.me/ivan_petrov" in html


def test_render_ticket_report_csv_sanitizes_formula_like_cells() -> None:
    report = TicketReport(
        public_id=uuid4(),
        public_number="HD-ARCH0002",
        client_chat_id=3003,
        status=TicketStatus.CLOSED,
        priority="high",
        subject="=cmd|' /C calc'!A0",
        assigned_operator_id=7,
        assigned_operator_name="@bad",
        assigned_operator_telegram_user_id=1001,
        created_at=datetime(2026, 4, 7, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 7, 13, 0, tzinfo=UTC),
        first_response_at=None,
        first_response_seconds=None,
        closed_at=datetime(2026, 4, 7, 14, 0, tzinfo=UTC),
        category_code="access",
        category_title="Доступ и вход",
        tags=("+urgent",),
        feedback=None,
        messages=(
            TicketReportMessage(
                sender_type=TicketMessageSenderType.CLIENT,
                sender_operator_name=None,
                text="-danger",
                created_at=datetime(2026, 4, 7, 12, 1, tzinfo=UTC),
                attachment=None,
            ),
        ),
        events=(),
    )

    csv_bytes = render_ticket_report_csv(report)
    csv_text = csv_bytes.decode("utf-8-sig")

    assert "'=cmd|' /C calc'!A0" in csv_text
    assert "'@bad" in csv_text
    assert "'+urgent" in csv_text
    assert "'-danger" in csv_text


def test_render_analytics_snapshot_html_contains_svg_charts() -> None:
    snapshot = HelpdeskAnalyticsSnapshot(
        window=AnalyticsWindow.DAYS_7,
        total_open_tickets=8,
        queued_tickets_count=2,
        assigned_tickets_count=4,
        escalated_tickets_count=1,
        closed_tickets_count=11,
        tickets_per_operator=(
            OperatorTicketLoad(operator_id=7, display_name="Иван Петров", ticket_count=3),
            OperatorTicketLoad(operator_id=8, display_name="Анна Смирнова", ticket_count=2),
        ),
        period_created_tickets_count=14,
        period_closed_tickets_count=9,
        average_first_response_time_seconds=420,
        average_resolution_time_seconds=8100,
        satisfaction_average=4.7,
        feedback_count=6,
        feedback_coverage_percent=67,
        rating_distribution=(
            AnalyticsRatingBucket(rating=5, count=4),
            AnalyticsRatingBucket(rating=4, count=2),
        ),
        operator_snapshots=(
            AnalyticsOperatorSnapshot(
                operator_id=7,
                display_name="Иван Петров",
                active_ticket_count=3,
                closed_ticket_count=5,
                average_first_response_time_seconds=360,
                average_resolution_time_seconds=7200,
                average_satisfaction=4.8,
                feedback_count=4,
            ),
        ),
        category_snapshots=(
            AnalyticsCategorySnapshot(
                category_id=2,
                category_title="Доступ и вход",
                created_ticket_count=6,
                open_ticket_count=2,
                closed_ticket_count=4,
                average_satisfaction=4.6,
                feedback_count=3,
                sla_breach_count=1,
            ),
        ),
        best_operators_by_closures=(
            AnalyticsOperatorSnapshot(
                operator_id=7,
                display_name="Иван Петров",
                active_ticket_count=3,
                closed_ticket_count=5,
                average_first_response_time_seconds=360,
                average_resolution_time_seconds=7200,
                average_satisfaction=4.8,
                feedback_count=4,
            ),
        ),
        best_operators_by_satisfaction=(
            AnalyticsOperatorSnapshot(
                operator_id=7,
                display_name="Иван Петров",
                active_ticket_count=3,
                closed_ticket_count=5,
                average_first_response_time_seconds=360,
                average_resolution_time_seconds=7200,
                average_satisfaction=4.8,
                feedback_count=4,
            ),
        ),
        top_categories=(
            AnalyticsCategorySnapshot(
                category_id=2,
                category_title="Доступ и вход",
                created_ticket_count=6,
                open_ticket_count=2,
                closed_ticket_count=4,
                average_satisfaction=4.6,
                feedback_count=3,
                sla_breach_count=1,
            ),
        ),
        first_response_breach_count=1,
        resolution_breach_count=2,
        sla_categories=(
            AnalyticsCategorySnapshot(
                category_id=2,
                category_title="Доступ и вход",
                created_ticket_count=6,
                open_ticket_count=2,
                closed_ticket_count=4,
                average_satisfaction=4.6,
                feedback_count=3,
                sla_breach_count=1,
            ),
        ),
    )

    html = render_analytics_snapshot_html(snapshot, AnalyticsSection.OVERVIEW).decode("utf-8")

    assert "HTML отчёт с графиками" in html
    assert "Статусный портрет" in html
    assert "<svg" in html
