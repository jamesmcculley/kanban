"""Tag parsing (pure: no I/O)."""

from __future__ import annotations

import re

_TAG = re.compile(r"[a-z][a-z0-9_-]*")
_TITLE_TAG = re.compile(r"(?:^|(?<=\s))#([A-Za-z][A-Za-z0-9_-]*)(?![\w-])")


def parse_tags(value) -> list[str]:
    """'#Home, errand  home' -> ['home', 'errand']: lowercase, deduped, order kept."""
    parts = re.split(r"[,\s]+", value) if isinstance(value, str) else [str(v) for v in value or []]
    tags: list[str] = []
    for part in parts:
        tag = part.strip().lstrip("#").lower()
        if _TAG.fullmatch(tag) and tag not in tags:
            tags.append(tag)
    return tags


def split_tags(title: str) -> tuple[str, list[str]]:
    """'Buy paint #home #errand' -> ('Buy paint', ['home', 'errand'])."""
    tags = parse_tags(_TITLE_TAG.findall(title))
    return " ".join(_TITLE_TAG.sub("", title).split()), tags
