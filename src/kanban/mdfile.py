"""Markdown files with YAML frontmatter: the on-disk format for boards and cards."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "board"


def read_md(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        _, front, body = text.split("---\n", 2)
        return yaml.safe_load(front) or {}, body.lstrip("\n")
    return {}, text


def write_md(path: Path, meta: dict, body: str = "") -> None:
    """Write via a temp file + atomic rename, not path.write_text() directly -- a plain write
    truncates the file before the new content lands, so a concurrent read (the sidebar's stats
    fetch races card writes constantly) can see a half-written file and crash on missing keys.
    os.replace() (what Path.replace() uses) is atomic on POSIX and Windows: a reader always sees
    either the whole old file or the whole new one, never a partial one."""
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(f"---\n{front}---\n\n{body}", encoding="utf-8")
    tmp.replace(path)


def extra_fields(meta: dict, known: set[str] | tuple[str, ...]) -> dict:
    """Frontmatter keys we do not understand. Written back unchanged (another tool, or a newer
    version, may own them), so an edit here never silently strips them."""
    return {k: v for k, v in meta.items() if k not in known}
