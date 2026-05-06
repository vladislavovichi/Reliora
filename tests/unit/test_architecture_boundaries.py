from __future__ import annotations

from pathlib import Path

from ops.scripts.check_architecture_boundaries import check_boundaries


def test_forbidden_imports_are_detected(tmp_path: Path) -> None:
    bot_file = tmp_path / "src" / "bot" / "handler.py"
    bot_file.parent.mkdir(parents=True)
    bot_file.write_text(
        "from application.services.helpdesk.service import HelpdeskService\n"
        "from infrastructure.db.session import build_session_factory\n",
        encoding="utf-8",
    )

    violations = check_boundaries(tmp_path)

    assert violations == [
        (
            "src/bot/handler.py:1: forbidden import application.services.helpdesk.service "
            "(bot must use backend/client contracts instead of the in-process helpdesk service)"
        ),
        (
            "src/bot/handler.py:2: forbidden import infrastructure.db.session "
            "(bot must not reach around application/backend APIs into database adapters)"
        ),
    ]


def test_import_safe_cases_do_not_fail(tmp_path: Path) -> None:
    bot_file = tmp_path / "src" / "bot" / "handler.py"
    backend_file = tmp_path / "src" / "backend" / "runtime.py"
    application_file = tmp_path / "src" / "application" / "service.py"
    bot_file.parent.mkdir(parents=True)
    backend_file.parent.mkdir(parents=True)
    application_file.parent.mkdir(parents=True)
    bot_file.write_text(
        "from application.contracts.runtime import TicketLockManager\n",
        encoding="utf-8",
    )
    backend_file.write_text(
        "from infrastructure.redis.runtime import RedisWorkflowRuntime\n",
        encoding="utf-8",
    )
    application_file.write_text(
        "from application.contracts.runtime import EXPECTED_DIAGNOSTICS_FAILURES\n",
        encoding="utf-8",
    )

    assert check_boundaries(tmp_path) == []
