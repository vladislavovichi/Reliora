from __future__ import annotations

from application.services.stats import (
    AnalyticsCategorySnapshot,
    AnalyticsOperatorSnapshot,
    AnalyticsRatingBucket,
    AnalyticsWindow,
    HelpdeskAnalyticsSnapshot,
    HelpdeskOperationalStats,
    OperatorTicketLoad,
)
from bot.formatters.operator_stats import (
    format_analytics_overview,
    format_category_analytics,
    format_operational_stats,
    format_operator_analytics,
    format_quality_analytics,
    format_sla_analytics,
)
from bot.keyboards.inline.operator_stats import build_operator_stats_markup


def test_format_operational_stats_returns_operator_friendly_text() -> None:
    stats = HelpdeskOperationalStats(
        total_open_tickets=6,
        queued_tickets_count=2,
        assigned_tickets_count=3,
        escalated_tickets_count=1,
        closed_tickets_count=4,
        tickets_per_operator=(
            OperatorTicketLoad(operator_id=7, display_name="Operator One", ticket_count=3),
            OperatorTicketLoad(operator_id=9, display_name="Operator Two", ticket_count=1),
        ),
        average_first_response_time_seconds=125,
        average_resolution_time_seconds=7260,
    )

    result = format_operational_stats(stats)

    assert result.startswith("Статистика")
    assert "Открытые заявки: 6" in result
    assert "Нагрузка по операторам" in result
    assert "- Operator One (id=7): 3" in result


def test_format_analytics_overview_returns_structured_premium_text() -> None:
    snapshot = _build_snapshot()

    result = format_analytics_overview(snapshot)

    assert result.startswith("Общая · 7 дней")
    assert "Сейчас" in result
    assert "Открытые · 6" in result
    assert "За период" in result
    assert "Средний рейтинг · 4,7 / 5" in result
    assert "Покрытие обратной связью · 80%" in result


def test_format_operator_analytics_shows_load_and_rankings() -> None:
    snapshot = _build_snapshot()

    result = format_operator_analytics(snapshot)

    assert result.startswith("Операторы · 7 дней")
    assert "Текущая нагрузка" in result
    assert "- Operator One · 3" in result
    assert "По закрытиям" in result
    assert "4 закрыто" in result
    assert "По качеству" in result
    assert "4,8 / 5" in result


def test_format_category_analytics_shows_reasons_and_distribution() -> None:
    snapshot = _build_snapshot()

    result = format_category_analytics(snapshot)

    assert result.startswith("Темы · 7 дней")
    assert "Топ причин" in result
    assert "- Доступ и вход · 5" in result
    assert "Открытые сейчас" in result
    assert "Закрыто за период" in result


def test_format_quality_analytics_shows_distribution_and_quality_leaders() -> None:
    snapshot = _build_snapshot()

    result = format_quality_analytics(snapshot)

    assert result.startswith("Качество · 7 дней")
    assert "Распределение" in result
    assert "- 5 · 3" in result
    assert "Лучшие по качеству" in result
    assert "Темы с лучшей обратной связью" in result


def test_format_sla_analytics_shows_breaches_and_categories() -> None:
    snapshot = _build_snapshot()

    result = format_sla_analytics(snapshot)

    assert result.startswith("SLA · 7 дней")
    assert "Нарушения" in result
    assert "Первый ответ · 2" in result
    assert "Темы с нарушениями" in result
    assert "- Доступ и вход · 2" in result


def test_build_operator_stats_markup_contains_sections_and_windows() -> None:
    markup = build_operator_stats_markup(
        section="overview",
        window=AnalyticsWindow.DAYS_7,
    )
    rows = tuple(tuple(button.text for button in row) for row in markup.inline_keyboard)

    assert rows == (
        ("• Общая", "Операторы", "Темы"),
        ("Качество", "SLA"),
        ("Сегодня", "• 7 дн", "30 дн", "Всё"),
    )


def _build_snapshot() -> HelpdeskAnalyticsSnapshot:
    operators = (
        AnalyticsOperatorSnapshot(
            operator_id=7,
            display_name="Operator One",
            active_ticket_count=3,
            closed_ticket_count=4,
            average_first_response_time_seconds=120,
            average_resolution_time_seconds=5400,
            average_satisfaction=4.8,
            feedback_count=3,
        ),
        AnalyticsOperatorSnapshot(
            operator_id=9,
            display_name="Operator Two",
            active_ticket_count=1,
            closed_ticket_count=1,
            average_first_response_time_seconds=240,
            average_resolution_time_seconds=9000,
            average_satisfaction=4.0,
            feedback_count=1,
        ),
    )
    categories = (
        AnalyticsCategorySnapshot(
            category_id=1,
            category_title="Доступ и вход",
            created_ticket_count=5,
            open_ticket_count=2,
            closed_ticket_count=3,
            average_satisfaction=4.5,
            feedback_count=2,
            sla_breach_count=2,
        ),
        AnalyticsCategorySnapshot(
            category_id=2,
            category_title="Платежи",
            created_ticket_count=3,
            open_ticket_count=1,
            closed_ticket_count=2,
            average_satisfaction=5.0,
            feedback_count=2,
            sla_breach_count=0,
        ),
    )
    return HelpdeskAnalyticsSnapshot(
        window=AnalyticsWindow.DAYS_7,
        total_open_tickets=6,
        queued_tickets_count=2,
        assigned_tickets_count=3,
        escalated_tickets_count=1,
        closed_tickets_count=4,
        tickets_per_operator=(
            OperatorTicketLoad(operator_id=7, display_name="Operator One", ticket_count=3),
            OperatorTicketLoad(operator_id=9, display_name="Operator Two", ticket_count=1),
        ),
        period_created_tickets_count=9,
        period_closed_tickets_count=5,
        average_first_response_time_seconds=126,
        average_resolution_time_seconds=7260,
        satisfaction_average=4.7,
        feedback_count=4,
        feedback_coverage_percent=80,
        rating_distribution=(
            AnalyticsRatingBucket(rating=5, count=3),
            AnalyticsRatingBucket(rating=4, count=1),
        ),
        operator_snapshots=operators,
        category_snapshots=categories,
        best_operators_by_closures=operators,
        best_operators_by_satisfaction=operators,
        top_categories=categories,
        first_response_breach_count=2,
        resolution_breach_count=1,
        sla_categories=(categories[0],),
    )
