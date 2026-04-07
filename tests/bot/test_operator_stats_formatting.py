from __future__ import annotations

from application.services.stats import HelpdeskOperationalStats, OperatorTicketLoad
from bot.formatters.operator import format_operational_stats


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
    assert "В очереди: 2" in result
    assert "Назначенные: 3" in result
    assert "Эскалированные: 1" in result
    assert "Закрытые: 4" in result
    assert "Нагрузка по операторам" in result
    assert "- Operator One (id=7): 3" in result
    assert "- Operator Two (id=9): 1" in result
    assert "Среднее время" in result
    assert "Первый ответ: 2 мин" in result
    assert "Решение: 2 ч 1 мин" in result
