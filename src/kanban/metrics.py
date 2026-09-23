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
    writer.writerow(["completed_at", "title", "board", "list", "repeating"])
    for e in sorted(events, key=lambda e: e["at"]):
        writer.writerow([e["at"], e["title"], e["board_title"], e["list"], "yes" if e.get("repeat") else ""])
    return buf.getvalue()
