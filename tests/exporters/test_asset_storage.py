from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketAttachmentKind
from infrastructure.assets.storage import LocalTicketAssetStorage


async def test_local_ticket_asset_storage_downloads_file_into_assets(tmp_path: Path) -> None:
    bot = Mock()

    async def download(file: str, destination: Path, **_: object) -> None:
        assert file == "telegram-file-id"
        destination.write_bytes(b"hello")

    bot.download = AsyncMock(side_effect=download)
    storage = LocalTicketAssetStorage(tmp_path)

    attachment = await storage.save_telegram_attachment(
        bot,
        attachment=TicketAttachmentDetails(
            kind=TicketAttachmentKind.DOCUMENT,
            telegram_file_id="telegram-file-id",
            telegram_file_unique_id="unique-file-id",
            filename="guide.pdf",
            mime_type="application/pdf",
        ),
    )

    assert attachment.storage_path == "document/unique-file-id.pdf"
    assert (tmp_path / "document" / "unique-file-id.pdf").read_bytes() == b"hello"


def test_local_ticket_asset_storage_rejects_path_escape(tmp_path: Path) -> None:
    storage = LocalTicketAssetStorage(tmp_path)

    try:
        storage.resolve_path("../etc/passwd")
    except ValueError as exc:
        assert "unsafe storage path" in str(exc)
    else:
        raise AssertionError("expected ValueError")


async def test_local_ticket_asset_storage_propagates_download_failure(tmp_path: Path) -> None:
    bot = Mock()
    bot.download = AsyncMock(side_effect=FileNotFoundError("telegram file missing"))
    storage = LocalTicketAssetStorage(tmp_path)

    with pytest.raises(FileNotFoundError):
        await storage.save_telegram_attachment(
            bot,
            attachment=TicketAttachmentDetails(
                kind=TicketAttachmentKind.DOCUMENT,
                telegram_file_id="missing-file-id",
                telegram_file_unique_id="missing-file",
                filename="guide.pdf",
                mime_type="application/pdf",
            ),
        )
