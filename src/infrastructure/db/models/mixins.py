from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum as PythonEnum

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


def utcnow() -> datetime:
    return datetime.now(UTC)


def enum_values(enum_cls: type[PythonEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )
