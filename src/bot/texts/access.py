from __future__ import annotations

from application.services.authorization import Permission


def get_permission_denied_text(permission: Permission) -> str:
    if permission in {Permission.MANAGE_OPERATORS, Permission.ACCESS_ADMIN}:
        return "Это действие доступно только супер администраторам."
    return "Это действие доступно только операторам и супер администраторам."
