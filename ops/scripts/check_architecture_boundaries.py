from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ForbiddenImportRule:
    source_root: Path
    forbidden_module: str
    reason: str


@dataclass(frozen=True, slots=True)
class ImportAllowlistEntry:
    path: Path
    module: str
    reason: str


FORBIDDEN_IMPORT_RULES = (
    ForbiddenImportRule(
        source_root=Path("src/bot"),
        forbidden_module="application.services.helpdesk",
        reason="bot must use backend/client contracts instead of the in-process helpdesk service",
    ),
    ForbiddenImportRule(
        source_root=Path("src/bot"),
        forbidden_module="infrastructure.db",
        reason="bot must not reach around application/backend APIs into database adapters",
    ),
    ForbiddenImportRule(
        source_root=Path("src/backend"),
        forbidden_module="app",
        reason="backend is a runtime entrypoint and must not depend on bot/app composition",
    ),
    ForbiddenImportRule(
        source_root=Path("src/application"),
        forbidden_module="infrastructure",
        reason="application must depend on contracts, not infrastructure implementations",
    ),
)

# No production exceptions are currently justified. Keep this list explicit so any future
# exception must document the owning file, imported module, and reason.
IMPORT_ALLOWLIST: tuple[ImportAllowlistEntry, ...] = ()


def main() -> int:
    violations = check_boundaries(Path.cwd())
    if violations:
        print("Architecture boundary violations found:")
        for violation in violations:
            print(f"  {violation}")
        return 1
    return 0


def check_boundaries(project_root: Path) -> list[str]:
    violations: list[str] = []
    for rule in FORBIDDEN_IMPORT_RULES:
        scan_root = project_root / rule.source_root
        if not scan_root.exists():
            continue
        for path in sorted(scan_root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            relative_path = path.relative_to(project_root)
            for node in ast.walk(tree):
                for module in _imported_modules(node):
                    if not _matches_module(module, rule.forbidden_module):
                        continue
                    if _is_allowlisted(relative_path, module):
                        continue
                    line_number = getattr(node, "lineno", 0)
                    violations.append(
                        f"{relative_path}:{line_number}: forbidden import {module} ({rule.reason})"
                    )
    return violations


def _imported_modules(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return (node.module,)
    return ()


def _is_allowlisted(path: Path, module: str) -> bool:
    return any(
        path == entry.path and _matches_module(module, entry.module) for entry in IMPORT_ALLOWLIST
    )


def _matches_module(module: str, boundary: str) -> bool:
    return module == boundary or module.startswith(f"{boundary}.")


if __name__ == "__main__":
    raise SystemExit(main())
