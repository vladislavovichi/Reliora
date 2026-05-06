from __future__ import annotations

import pytest

from bot.handlers.common.ticket_attachments import (
    AttachmentRejectedError,
    _ensure_document_is_safe,
    _ensure_size_allowed,
    _normalize_filename,
)
from bot.texts.common import ATTACHMENT_TOO_LARGE_TEXT, ATTACHMENT_UNSAFE_TEXT
from domain.enums.tickets import TicketAttachmentKind
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


def test_document_attachment_rejects_blocked_extension() -> None:
    with pytest.raises(AttachmentRejectedError) as exc_info:
        _ensure_document_is_safe(
            filename="../payload.sh",
            mime_type="text/plain",
            limits=AttachmentLimitsConfig(),
        )

    assert str(exc_info.value) == ATTACHMENT_UNSAFE_TEXT


def test_attachment_rejects_oversized_document() -> None:
    with pytest.raises(AttachmentRejectedError) as exc_info:
        _ensure_size_allowed(
            kind=TicketAttachmentKind.DOCUMENT,
            size_bytes=AttachmentLimitsConfig().document_max_bytes + 1,
            limits=AttachmentLimitsConfig(),
        )

    assert str(exc_info.value) == ATTACHMENT_TOO_LARGE_TEXT
