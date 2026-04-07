from __future__ import annotations

from application.services.authorization import Permission, get_permission_denied_message


def get_permission_denied_text(permission: Permission) -> str:
    return get_permission_denied_message(permission)
