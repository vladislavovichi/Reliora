from __future__ import annotations

import ast
from pathlib import Path

BOT_ROOT = Path("src/bot")
FORBIDDEN_IMPORTS = (
    "application.services.helpdesk",
    "application.services.helpdesk.service",
    "infrastructure.db",
)


def main() -> int:
    violations: list[str] = []
    for path in sorted(BOT_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported_modules = _imported_modules(node)
            for module in imported_modules:
                if _is_forbidden(module):
                    violations.append(f"{path}:{node.lineno}: forbidden import {module}")

    if violations:
        print("Architecture boundary violations found:")
        for violation in violations:
            print(f"  {violation}")
        return 1
    return 0


def _imported_modules(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return (node.module,)
    return ()


def _is_forbidden(module: str) -> bool:
    return any(
        module == forbidden or module.startswith(f"{forbidden}.") for forbidden in FORBIDDEN_IMPORTS
    )


if __name__ == "__main__":
    raise SystemExit(main())
