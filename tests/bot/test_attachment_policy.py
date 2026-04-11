from __future__ import annotations

import pytest

from bot.handlers.common.ticket_attachments import (
    AttachmentRejectedError,
    _ensure_document_is_safe,
    _normalize_filename,
)
from bot.texts.common import ATTACHMENT_UNSAFE_TEXT
from infrastructure.config.settings import AttachmentLimitsConfig


def test_document_attachment_rejects_blocked_mime_type() -> None:
    with pytest.raises(AttachmentRejectedError) as exc_info:
        _ensure_document_is_safe(
            filename="report.pdf",
            mime_type="application/x-msdownload",
            limits=AttachmentLimitsConfig(),
        )

    assert str(exc_info.value) == ATTACHMENT_UNSAFE_TEXT


def test_normalize_filename_keeps_only_safe_basename() -> None:
    assert _normalize_filename("../../Quarterly  report.pdf") == "Quarterly report.pdf"
