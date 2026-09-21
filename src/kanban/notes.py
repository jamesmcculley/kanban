"""Card notes: Markdown rendering plus checklist (`- [ ]`) support.

Raw HTML in notes is escaped (never passed through), and links with unsafe schemes such as
`javascript:` are left as plain text by markdown-it's link validation.
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt
from markupsafe import Markup

_md = MarkdownIt("commonmark", {"html": False, "breaks": True}).enable(["strikethrough", "table"])
_TASK_TEXT = re.compile(r"\[( |x|X)\](\s|$)")
_TASK_LINE = re.compile(r"^(\s*(?:>\s*)*(?:[-*+]|\d+[.)])\s+)\[( |x|X)\]")
_TASK_HTML = re.compile(r"(<li>\s*(?:<p>)?)\[( |x|X)\](?=\s)")


def tasks(body: str) -> list[tuple[int, bool]]:
    """(source line, checked) for each list item that starts with [ ] or [x], in order."""
    found: list[tuple[int, bool]] = []
    tokens = _md.parse(body)
    for i, tok in enumerate(tokens):
        if tok.type != "list_item_open" or not tok.map:
            continue
        inline = next((t for t in tokens[i + 1:i + 4] if t.type == "inline"), None)
        if inline and (m := _TASK_TEXT.match(inline.content)):
            found.append((tok.map[0], m[1] != " "))
    return found


def progress(body: str) -> tuple[int, int]:
    """(done, total) checklist items; (0, 0) when the notes have no checklist."""
    items = tasks(body or "")
    return sum(1 for _, checked in items if checked), len(items)


def toggle_task(body: str, n: int) -> str:
    """Flip the n-th checklist item in the notes' Markdown source."""
    items = tasks(body)
    if not 0 <= n < len(items):
        raise IndexError(n)
    lines = body.split("\n")
    line = items[n][0]
    lines[line] = _TASK_LINE.sub(
        lambda m: f"{m[1]}[{' ' if m[2] != ' ' else 'x'}]", lines[line], count=1)
    return "\n".join(lines)


def render(body: str, task_url: str | None = None, target: str = "") -> Markup:
    """HTML for the notes. With `task_url` (containing "{n}"), checklist boxes become live
    htmx checkboxes that POST there and swap the response into `target`."""
    html = _md.render(body or "")
    html = html.replace("<a href=", '<a target="_blank" rel="noopener noreferrer" href=')
    counter = iter(range(10_000))

    def box(m: re.Match) -> str:
        n = next(counter)
        checked = " checked" if m[2] != " " else ""
        live = (f' hx-post="{task_url.format(n=n)}" hx-target="{target}" hx-swap="outerHTML"'
                if task_url else " disabled")
        return f'{m[1]}<input type="checkbox" class="task" data-task="{n}"{checked}{live}>'

    return Markup(_TASK_HTML.sub(box, html))
