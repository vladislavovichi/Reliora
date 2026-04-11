from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.base import Base
from infrastructure.db.models.mixins import CreatedAtMixin


class OperatorInviteCode(CreatedAtMixin, Base):
    __tablename__ = "operator_invite_codes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    created_by_telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    max_uses: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    used_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_telegram_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
