from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    OPERATOR = "operator"
    USER = "user"
