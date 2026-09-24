"""Pure aggregation over Logbook events, for the Metrics page and the activity CSV export.

No I/O, no Flask -- see AGENTS.md's boundary list. `events` is whatever Store.logbook() returns:
dicts with at least `at` (an ISO date or datetime string), `title`, `board_title` and `list`.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import date

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def by_board(events: list[dict]) -> list[tuple[str, int]]:
    """Busiest board first."""
    return Counter(e["board_title"] for e in events).most_common()


def by_weekday(events: list[dict]) -> list[tuple[str, int]]:
    """Always all seven days, Monday first, zeros included -- a bar chart with gaps in it would
    read as a data problem rather than "you didn't do anything that day"."""
    counts = Counter(date.fromisoformat(e["at"][:10]).weekday() for e in events)
    return [(name, counts.get(i, 0)) for i, name in enumerate(WEEKDAYS)]


def to_csv(events: list[dict]) -> str:
    """Oldest first -- a natural reading order for a downloaded log, unlike the Logbook page
    itself (newest-first, for scanning what you just did)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["completed_at", "title", "board", "list", "priority", "tags", "repeating"])
    for e in sorted(events, key=lambda e: e["at"]):
        writer.writerow([e["at"], e["title"], e["board_title"], e["list"], e.get("priority", ""),
                         " ".join(e.get("tags") or []), "yes" if e.get("repeat") else ""])
    return buf.getvalue()


def filter_events(events: list[dict], q: str = "", tags: list[str] | None = None,
                  priorities: list[str] | None = None, boards: list[str] | None = None) -> list[dict]:
    """Narrow an already date-filtered event list by title text, tags, priority and board -- each
    optional, and an empty/missing filter matches everything (same "nothing checked = no
    narrowing" convention as the per-board filter, filter.js). `tags` and `priority` only ever
    match events logged since those started being recorded (see logbook.py's `_event`); older
    entries simply never match a tag or priority filter, same as a card with none set wouldn't."""
    q = (q or "").strip().lower()
    tag_set, priority_set, board_set = set(tags or []), set(priorities or []), set(boards or [])

    def matches(e: dict) -> bool:
        if q and q not in e["title"].lower():
            return False
        if tag_set and not tag_set & set(e.get("tags") or []):
            return False
        if priority_set and (e.get("priority") or "none") not in priority_set:
            return False
        return not (board_set and e["board"] not in board_set)

    return [e for e in events if matches(e)]
