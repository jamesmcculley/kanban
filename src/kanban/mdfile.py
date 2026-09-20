"""Markdown files with YAML frontmatter: the on-disk format for boards, cards and canvas items."""

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
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{front}---\n\n{body}", encoding="utf-8")
