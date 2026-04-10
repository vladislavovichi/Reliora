from __future__ import annotations

from application.services.stats import (
    AnalyticsCategorySnapshot,
    AnalyticsOperatorSnapshot,
    AnalyticsWindow,
    HelpdeskAnalyticsSnapshot,
    HelpdeskOperationalStats,
    OperatorTicketLoad,
    get_analytics_window_label,
)
from bot.formatters.operator_primitives import format_duration

AnalyticsSection = str


def format_operational_stats(stats: HelpdeskOperationalStats) -> str:
    lines = [
        "Статистика",
        f"Открытые заявки: {stats.total_open_tickets}",
        f"В очереди: {stats.queued_tickets_count}",
        f"В работе: {stats.assigned_tickets_count}",
        f"На эскалации: {stats.escalated_tickets_count}",
        f"Закрытые: {stats.closed_tickets_count}",
        "",
        "Нагрузка по операторам",
    ]

    if not stats.tickets_per_operator:
        lines.append("- активных назначений нет")
    else:
        for item in stats.tickets_per_operator:
            lines.append(f"- {item.display_name} (id={item.operator_id}): {item.ticket_count}")

    lines.extend(
        [
            "",
            "Среднее время",
            f"Первый ответ: {format_duration(stats.average_first_response_time_seconds)}",
            f"Решение: {format_duration(stats.average_resolution_time_seconds)}",
        ]
    )
    return "\n".join(lines)


def format_analytics_section(
    snapshot: HelpdeskAnalyticsSnapshot,
    *,
    section: AnalyticsSection,
) -> str:
    if section == "operators":
        return format_operator_analytics(snapshot)
    if section == "topics":
        return format_category_analytics(snapshot)
    if section == "quality":
        return format_quality_analytics(snapshot)
    if section == "sla":
        return format_sla_analytics(snapshot)
    return format_analytics_overview(snapshot)


def format_analytics_overview(snapshot: HelpdeskAnalyticsSnapshot) -> str:
    lines = [
        _header("Общая", snapshot.window),
        "",
        "Сейчас",
        f"Открытые · {snapshot.total_open_tickets}",
        f"В очереди · {snapshot.queued_tickets_count}",
        f"В работе · {snapshot.assigned_tickets_count}",
        f"Эскалация · {snapshot.escalated_tickets_count}",
        f"Закрытые всего · {snapshot.closed_tickets_count}",
        "",
        "За период",
        f"Новые · {snapshot.period_created_tickets_count}",
        f"Закрыто · {snapshot.period_closed_tickets_count}",
        f"Оценок · {snapshot.feedback_count}",
        f"Средний рейтинг · {_format_rating(snapshot.satisfaction_average)}",
        f"Покрытие обратной связью · {_format_percent(snapshot.feedback_coverage_percent)}",
        "",
        "Скорость",
        f"Первый ответ · {format_duration(snapshot.average_first_response_time_seconds)}",
        f"Решение · {format_duration(snapshot.average_resolution_time_seconds)}",
        "",
        "Нагрузка",
    ]
    lines.extend(
        _format_load_lines(
            snapshot.tickets_per_operator,
            empty="Активных назначений сейчас нет.",
        )
    )
    return "\n".join(lines)


def format_operator_analytics(snapshot: HelpdeskAnalyticsSnapshot) -> str:
    lines = [
        _header("Операторы", snapshot.window),
        "",
        "Текущая нагрузка",
    ]
    lines.extend(
        _format_load_lines(snapshot.tickets_per_operator, empty="Сейчас нет активных назначений.")
    )
    lines.extend(["", "По закрытиям"])
    lines.extend(
        _format_operator_ranking(
            snapshot.best_operators_by_closures,
            primary="closed",
            empty="За период закрытий пока нет.",
        )
    )
    lines.extend(["", "По качеству"])
    lines.extend(
        _format_operator_ranking(
            snapshot.best_operators_by_satisfaction,
            primary="quality",
            empty="Оценок по операторам пока недостаточно.",
        )
    )
    return "\n".join(lines)


def format_category_analytics(snapshot: HelpdeskAnalyticsSnapshot) -> str:
    lines = [
        _header("Темы", snapshot.window),
        "",
        "Топ причин",
    ]
    lines.extend(
        _format_category_lines(
            snapshot.top_categories,
            mode="created",
            empty="За период тем с активностью пока нет.",
        )
    )
    lines.extend(["", "Открытые сейчас"])
    lines.extend(
        _format_category_lines(
            tuple(item for item in snapshot.category_snapshots if item.open_ticket_count > 0)[:5],
            mode="open",
            empty="Открытых заявок по темам сейчас нет.",
        )
    )
    lines.extend(["", "Закрыто за период"])
    lines.extend(
        _format_category_lines(
            tuple(item for item in snapshot.category_snapshots if item.closed_ticket_count > 0)[:5],
            mode="closed",
            empty="Закрытий по темам за период пока нет.",
        )
    )
    return "\n".join(lines)


def format_quality_analytics(snapshot: HelpdeskAnalyticsSnapshot) -> str:
    lines = [
        _header("Качество", snapshot.window),
        "",
        "Общая картина",
        f"Средний рейтинг · {_format_rating(snapshot.satisfaction_average)}",
        f"Оценок · {snapshot.feedback_count}",
        f"Покрытие · {_format_percent(snapshot.feedback_coverage_percent)}",
        "",
        "Распределение",
    ]
    lines.extend(_format_rating_distribution(snapshot))
    lines.extend(["", "Лучшие по качеству"])
    lines.extend(
        _format_operator_ranking(
            snapshot.best_operators_by_satisfaction,
            primary="quality",
            empty="Пока недостаточно данных по оценкам операторов.",
        )
    )
    lines.extend(["", "Темы с лучшей обратной связью"])
    lines.extend(_format_best_categories_by_quality(snapshot))
    return "\n".join(lines)


def format_sla_analytics(snapshot: HelpdeskAnalyticsSnapshot) -> str:
    lines = [
        _header("SLA", snapshot.window),
        "",
        "Нарушения",
        f"Первый ответ · {snapshot.first_response_breach_count}",
        f"Решение · {snapshot.resolution_breach_count}",
        "",
        "Темы с нарушениями",
    ]
    lines.extend(
        _format_category_lines(
            snapshot.sla_categories,
            mode="sla",
            empty="Нарушений SLA по темам за период не найдено.",
        )
    )
    lines.extend(
        [
            "",
            "Средняя скорость",
            f"Первый ответ · {format_duration(snapshot.average_first_response_time_seconds)}",
            f"Решение · {format_duration(snapshot.average_resolution_time_seconds)}",
        ]
    )
    return "\n".join(lines)


def _header(title: str, window: AnalyticsWindow) -> str:
    return f"{title} · {get_analytics_window_label(window)}"


def _format_load_lines(
    loads: tuple[OperatorTicketLoad, ...],
    *,
    empty: str,
) -> list[str]:
    if not loads:
        return [empty]
    return [
        f"- {item.display_name} · {item.ticket_count}"
        for item in loads[:5]
    ]


def _format_operator_ranking(
    operators: tuple[AnalyticsOperatorSnapshot, ...],
    *,
    primary: str,
    empty: str,
) -> list[str]:
    if not operators:
        return [empty]

    lines: list[str] = []
    for item in operators[:5]:
        if primary == "quality":
            lines.append(
                f"- {item.display_name} · {_format_rating(item.average_satisfaction)} · "
                f"{item.feedback_count} оцен."
            )
            continue
        lines.append(
            f"- {item.display_name} · {item.closed_ticket_count} закрыто · "
            f"{format_duration(item.average_first_response_time_seconds)}"
        )
    return lines


def _format_category_lines(
    categories: tuple[AnalyticsCategorySnapshot, ...],
    *,
    mode: str,
    empty: str,
) -> list[str]:
    if not categories:
        return [empty]

    lines: list[str] = []
    for item in categories[:5]:
        if mode == "open":
            value = item.open_ticket_count
        elif mode == "closed":
            value = item.closed_ticket_count
        elif mode == "sla":
            value = item.sla_breach_count
        else:
            value = item.created_ticket_count
        lines.append(f"- {item.category_title} · {value}")
    return lines


def _format_rating_distribution(snapshot: HelpdeskAnalyticsSnapshot) -> list[str]:
    if not snapshot.rating_distribution:
        return ["Оценок за период пока нет."]
    return [f"- {item.rating} · {item.count}" for item in snapshot.rating_distribution]


def _format_best_categories_by_quality(snapshot: HelpdeskAnalyticsSnapshot) -> list[str]:
    best_categories = tuple(
        sorted(
            (
                item
                for item in snapshot.category_snapshots
                if item.average_satisfaction is not None and item.feedback_count > 0
            ),
            key=lambda item: (
                item.average_satisfaction or 0.0,
                item.feedback_count,
                item.category_title.lower(),
            ),
            reverse=True,
        )[:5]
    )
    if not best_categories:
        return ["Пока недостаточно данных по темам."]
    return [
        f"- {item.category_title} · {_format_rating(item.average_satisfaction)} · "
        f"{item.feedback_count} оцен."
        for item in best_categories
    ]


def _format_rating(value: float | None) -> str:
    if value is None:
        return "нет данных"
    return f"{value:.1f} / 5".replace(".", ",")


def _format_percent(value: int | None) -> str:
    if value is None:
        return "нет данных"
    return f"{value}%"
