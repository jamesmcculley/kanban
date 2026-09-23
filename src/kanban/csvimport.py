"""CSV import: turn spreadsheet rows into card-shaped dicts (pure: no I/O, no Store).

Header row required (case-insensitive; only "title" is needed). Recognized columns, with a couple
of common aliases: title (or name), list (or column/status), start, due, tags, priority,
notes (or body), done. Unknown columns are ignored, not an error -- a CSV exported from somewhere
else always has extra columns this app has no use for.
"""

from __future__ import annotations

import csv
import io

from .dates import parse_due
from .tags import parse_tags

_TRUE = {"true", "yes", "y", "1", "done", "x", "complete", "completed"}

EXAMPLE_CSV = (
    "title,list,due,tags,priority,notes,done\n"
    "Buy paint,Todo,in 3 days,home,,,\n"
    'Call the plumber,Todo,tomorrow,home errand,high,"Ask about the upstairs leak too",\n'
    "Finish the report,Doing,,work,medium,,\n"
    "Submitted expense report,Done,,work,,,yes\n"
)


def parse_csv(text: str) -> tuple[list[dict], list[str]]:
    """(rows, errors). Each row is ready for Store.import_cards: {title, list, start, due, tags,
    priority, notes, done}. A row with no title is skipped and reported, not silently dropped --
    Store itself is still the final word on whether a priority or column is valid."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], ["The file has no header row."]
    fields = {(f or "").strip().lower(): f for f in reader.fieldnames}

    def get(raw: dict, *keys: str) -> str:
        for k in keys:
            f = fields.get(k)
            if f and raw.get(f):
                return raw[f].strip()
        return ""

    rows: list[dict] = []
    errors: list[str] = []
    for i, raw in enumerate(reader, start=2):  # the header is row 1
        title = get(raw, "title", "name")
        if not title:
            errors.append(f"row {i}: no title, skipped")
            continue
        due_raw, start_raw = get(raw, "due"), get(raw, "start")
        due = parse_due(due_raw) if due_raw else None
        start = parse_due(start_raw) if start_raw else None
        if due_raw and not due:
            errors.append(f"row {i} ({title!r}): couldn't understand due date {due_raw!r}, left blank")
        if start_raw and not start:
            errors.append(f"row {i} ({title!r}): couldn't understand start date {start_raw!r}, left blank")
        rows.append({
            "title": title,
            "list": get(raw, "list", "column", "status"),
            "start": start.isoformat() if start else None,
            "due": due.isoformat() if due else None,
            "tags": parse_tags(get(raw, "tags")),
            "priority": get(raw, "priority").lower() or None,
            "notes": get(raw, "notes", "body"),
            "done": get(raw, "done").lower() in _TRUE,
        })
    return rows, errors
