from __future__ import annotations

from pathlib import Path


def test_mini_app_renderers_do_not_inject_known_user_fields_unescaped() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/mini_app/static/assets").glob("renderers*.js")
    )
    source += "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/mini_app/static/assets/renderers").glob("*.js")
    )
    unsafe_fragments = (
        "${item.subject}",
        "${ticket.subject}",
        "${message.text}",
        "${note.text}",
        "${macro.body}",
        "${suggestion.body}",
    )

    for fragment in unsafe_fragments:
        assert fragment not in source
