from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_TRACKED_PATH = re.compile(
    r"(^|/)(?:"
    r"__pycache__|\.mypy_cache|\.pytest_cache|\.ruff_cache|\.hypothesis|\.pyre|"
    r"htmlcov|build|dist|\.venv|venv|\.eggs|[^/]+\.egg-info"
    r")(?:/|$)|"
    r"^env/|"
    r"\.py[co]$|"
    r"(^|/)\.coverage(?:\..*)?$|"
    r"(^|/)coverage\.xml$"
)
FORBIDDEN_ENV_PATH = re.compile(r"(^|/)\.env(?:\..*)?$|^ops/env/(?!.*\.example$).+")
SECRET_PATTERNS = (
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{35,}\b"),
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9][A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgh[opsu]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
)
KEY_VALUE_SECRET = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|token|password|private[_-]?key)\b"
    r"\s*[:=]\s*['\"]?([^'\"\s#]+)"
)
ALLOWED_SECRET_VALUES = {
    "",
    "change-me",
    "changeme",
    "example",
    "fake",
    "helpdesk",
    "internal-test-token",
    "expected-token",
    "secret",
    "test",
    "test-internal-token",
    "token",
    "wrong-token",
}
SKIP_SECRET_SCAN_SUFFIXES = {
    ".lock",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
}


def main() -> int:
    tracked_files = _tracked_files()
    forbidden = _forbidden_artifacts(tracked_files)
    leaked_secrets = _scan_likely_secrets(tracked_files)
    if not forbidden and not leaked_secrets:
        return 0

    if forbidden:
        print("Forbidden generated/cache/secret artifacts are tracked:", file=sys.stderr)
        for path in forbidden:
            print(f"  {path}", file=sys.stderr)
    if leaked_secrets:
        print("Likely committed secrets detected:", file=sys.stderr)
        for finding in leaked_secrets:
            print(f"  {finding}", file=sys.stderr)
    return 1


def _tracked_files() -> list[str]:
    return subprocess.run(
        ["git", "ls-files"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()


def _forbidden_artifacts(tracked_files: list[str]) -> list[str]:
    return [
        path
        for path in tracked_files
        if FORBIDDEN_TRACKED_PATH.search(path)
        or (FORBIDDEN_ENV_PATH.search(path) and path != ".env.example")
    ]


def _scan_likely_secrets(tracked_files: list[str]) -> list[str]:
    findings: list[str] = []
    for path in tracked_files:
        source_path = Path(path)
        if source_path.suffix.lower() in SKIP_SECRET_SCAN_SUFFIXES:
            continue
        try:
            text = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _line_has_secret_literal(line) or _line_has_secret_assignment(line):
                findings.append(f"{path}:{line_number}")
    return findings


def _line_has_secret_literal(line: str) -> bool:
    return any(pattern.search(line) for pattern in SECRET_PATTERNS)


def _line_has_secret_assignment(line: str) -> bool:
    match = KEY_VALUE_SECRET.search(line)
    if match is None:
        return False
    value = match.group(1).strip().strip("'\"").lower()
    if value in ALLOWED_SECRET_VALUES:
        return False
    if any(fragment in value for fragment in (".", "(", ")", "[", "]")):
        return False
    if value.startswith(("${", "$", "<", "your_", "example_", "test_")):
        return False
    return len(value) >= 12


if __name__ == "__main__":
    raise SystemExit(main())
