from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

from starlette.responses import Response


@dataclass(slots=True, frozen=True)
class BinaryPayload:
    filename: str
    content_type: str
    content: bytes


class MiniAppJSONResponse(Response):
    media_type = "application/json; charset=utf-8"

    def __init__(
        self,
        content: dict[str, Any],
        *,
        status_code: int | HTTPStatus = HTTPStatus.OK,
    ) -> None:
        super().__init__(
            content=content,
            status_code=int(status_code),
            headers={"Cache-Control": "no-store"},
            media_type=self.media_type,
        )

    @staticmethod
    def render(content: dict[str, Any]) -> bytes:
        return json.dumps(content, ensure_ascii=False).encode("utf-8")


def json_response(
    payload: dict[str, Any],
    *,
    status_code: int | HTTPStatus = HTTPStatus.OK,
) -> MiniAppJSONResponse:
    return MiniAppJSONResponse(payload, status_code=status_code)


def binary_response(payload: BinaryPayload) -> Response:
    return Response(
        content=payload.content,
        media_type=payload.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{payload.filename}"',
            "Cache-Control": "no-store",
        },
    )


def static_file_response(
    path: Path,
    *,
    static_dir: Path,
    content_type: str | None = None,
) -> Response:
    resolved_base = static_dir.resolve()
    resolved_path = path.resolve()
    if resolved_base not in resolved_path.parents and resolved_path != resolved_base:
        return _static_not_found_response()
    if not resolved_path.is_file():
        return _static_not_found_response()

    guessed_type = content_type or mimetypes.guess_type(resolved_path.name)[0]
    return Response(
        content=resolved_path.read_bytes(),
        headers={
            "Content-Type": guessed_type or "application/octet-stream",
            "Cache-Control": "no-store",
        },
    )


def _static_not_found_response() -> MiniAppJSONResponse:
    return json_response(
        {"error": "Файл Mini App не найден."},
        status_code=HTTPStatus.NOT_FOUND,
    )
