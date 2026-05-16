from __future__ import annotations

from typing import Any

from application.services.stats import HelpdeskAnalyticsSnapshot


def serialize_analytics_snapshot(snapshot: HelpdeskAnalyticsSnapshot) -> dict[str, Any]:
    return {
        "window": snapshot.window.value,
        "total_open_tickets": snapshot.total_open_tickets,
        "queued_tickets_count": snapshot.queued_tickets_count,
        "assigned_tickets_count": snapshot.assigned_tickets_count,
        "escalated_tickets_count": snapshot.escalated_tickets_count,
        "closed_tickets_count": snapshot.closed_tickets_count,
        "period_created_tickets_count": snapshot.period_created_tickets_count,
        "period_closed_tickets_count": snapshot.period_closed_tickets_count,
        "average_first_response_time_seconds": snapshot.average_first_response_time_seconds,
        "average_resolution_time_seconds": snapshot.average_resolution_time_seconds,
        "satisfaction_average": snapshot.satisfaction_average,
        "feedback_count": snapshot.feedback_count,
        "feedback_coverage_percent": snapshot.feedback_coverage_percent,
        "tickets_per_operator": [
            {
                "operator_id": item.operator_id,
                "display_name": item.display_name,
                "ticket_count": item.ticket_count,
            }
            for item in snapshot.tickets_per_operator
        ],
        "rating_distribution": [
            {
                "rating": bucket.rating,
                "count": bucket.count,
            }
            for bucket in snapshot.rating_distribution
        ],
        "operator_snapshots": [
            {
                "operator_id": item.operator_id,
                "display_name": item.display_name,
                "active_ticket_count": item.active_ticket_count,
                "closed_ticket_count": item.closed_ticket_count,
                "average_first_response_time_seconds": item.average_first_response_time_seconds,
                "average_resolution_time_seconds": item.average_resolution_time_seconds,
                "average_satisfaction": item.average_satisfaction,
                "feedback_count": item.feedback_count,
            }
            for item in snapshot.operator_snapshots
        ],
        "category_snapshots": [
            _serialize_category_snapshot(item) for item in snapshot.category_snapshots
        ],
        "best_operators_by_closures": [
            {
                "operator_id": item.operator_id,
                "display_name": item.display_name,
                "active_ticket_count": item.active_ticket_count,
                "closed_ticket_count": item.closed_ticket_count,
                "average_first_response_time_seconds": item.average_first_response_time_seconds,
                "average_resolution_time_seconds": item.average_resolution_time_seconds,
                "average_satisfaction": item.average_satisfaction,
                "feedback_count": item.feedback_count,
            }
            for item in snapshot.best_operators_by_closures
        ],
        "best_operators_by_satisfaction": [
            {
                "operator_id": item.operator_id,
                "display_name": item.display_name,
                "active_ticket_count": item.active_ticket_count,
                "closed_ticket_count": item.closed_ticket_count,
                "average_first_response_time_seconds": item.average_first_response_time_seconds,
                "average_resolution_time_seconds": item.average_resolution_time_seconds,
                "average_satisfaction": item.average_satisfaction,
                "feedback_count": item.feedback_count,
            }
            for item in snapshot.best_operators_by_satisfaction
        ],
        "top_categories": [_serialize_category_snapshot(item) for item in snapshot.top_categories],
        "first_response_breach_count": snapshot.first_response_breach_count,
        "resolution_breach_count": snapshot.resolution_breach_count,
        "sla_categories": [_serialize_category_snapshot(item) for item in snapshot.sla_categories],
    }


def _serialize_category_snapshot(item: Any) -> dict[str, Any]:
    return {
        "category_id": item.category_id,
        "category_title": item.category_title,
        "created_ticket_count": item.created_ticket_count,
        "open_ticket_count": item.open_ticket_count,
        "closed_ticket_count": item.closed_ticket_count,
        "average_satisfaction": item.average_satisfaction,
        "feedback_count": item.feedback_count,
        "sla_breach_count": item.sla_breach_count,
    }
