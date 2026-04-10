from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, Mock

from infrastructure.assets.storage import LocalTicketAssetStorage
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketAttachmentKind


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
