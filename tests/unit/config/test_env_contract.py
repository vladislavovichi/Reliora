from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
ENV_README = REPO_ROOT / "ops/env/README.md"
REQUIRED_ENV_KEYS = {
    "AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS",
    "BACKEND_AUTH__TOKEN",
    "AI_SERVICE_AUTH__TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "DATABASE_URL",
    "REDIS_URL",
}
SAFE_PLACEHOLDERS = {
    "",
    "replace-me",
    "password",
    "user",
    "reliora",
    "telegram-bot",
    "helpdesk-backend",
}
SECRET_PATTERNS = (
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{35,}\b"),
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9][A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgh[opsu]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
)
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|token|password|private[_-]?key)\b"
    r"\s*=\s*([^#\s]+)"
)
REMOVED_ENV_KEYS = {
    "BOT__TOKEN",
    "DATABASE__URL",
    "REDIS__URL",
    "BOT_USERNAME",
    "AI__PROVIDER",
}
OBSOLETE_HOSTED_AI_KEYS = {
    "AI__API_TOKEN",
    "AI__BASE_URL",
    "AI__TIMEOUT_SECONDS",
}
KNOWN_ENV_FILES = {
    ".env",
    ".env.example",
    ".env.local",
    ".env.test",
}


def test_env_example_contains_required_settings_keys() -> None:
    keys = _env_example_values().keys()

    assert keys >= REQUIRED_ENV_KEYS


def test_env_example_contains_safe_placeholders() -> None:
    values = _env_example_values()

    assert values["TELEGRAM_BOT_TOKEN"] == "replace-me"
    assert values["DATABASE_URL"] == "postgresql+asyncpg://user:password@localhost:5432/reliora"
    assert values["REDIS_URL"] == "redis://localhost:6379/0"


def test_env_example_has_no_obvious_secrets() -> None:
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        assert not any(pattern.search(line) for pattern in SECRET_PATTERNS), line_number

        match = SECRET_ASSIGNMENT.search(line)
        if match is None:
            continue

        value = match.group(1).strip().strip("'\"")
        assert value.lower() in SAFE_PLACEHOLDERS, line_number


def test_docs_do_not_reference_missing_env_files() -> None:
    missing: list[str] = []
    for path in [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").rglob("*.md")), ENV_README]:
        text = path.read_text(encoding="utf-8")
        for reference in re.findall(r"(?:ops/env/[-\w./]+|\.env(?:\.[-\w]+)*)", text):
            if reference in KNOWN_ENV_FILES:
                continue
            if reference.startswith("ops/env/") and (REPO_ROOT / reference).exists():
                continue
            missing.append(f"{path.relative_to(REPO_ROOT)} -> {reference}")

    assert missing == []


def test_removed_env_names_are_not_documented_as_supported() -> None:
    values = _env_example_values()
    docs_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            REPO_ROOT / "README.md",
            *sorted((REPO_ROOT / "docs").rglob("*.md")),
            ENV_README,
        ]
    )

    assert REMOVED_ENV_KEYS.isdisjoint(values)
    assert OBSOLETE_HOSTED_AI_KEYS.isdisjoint(values)
    for key in REMOVED_ENV_KEYS | OBSOLETE_HOSTED_AI_KEYS:
        assert key not in docs_text


def _env_example_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        normalized = line.strip()
        if not normalized or normalized.startswith("#") or "=" not in normalized:
            continue
        key, value = normalized.split("=", 1)
        values[key] = value
    return values
