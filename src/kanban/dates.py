"""Tiny natural-language due-date parser (no dependencies).

Understands: today, tomorrow, monday..sunday (next occurrence), "next monday" (that weekday
in the following week), "in 3 days", "in 2 weeks", "jun 5", and ISO dates.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

_DAY_RE = "|".join(f"{d[:3]}(?:{d[3:]})?" for d in _DAYS)
_MONTH_RE = "|".join(f"{m}(?:[a-z]*)" for m in _MONTHS)
PHRASE = (
    r"today|tomorrow|tmrw"
    rf"|(?:next\s+)?(?:{_DAY_RE})"
    r"|in\s+\d+\s+(?:day|week)s?"
    rf"|(?:{_MONTH_RE})\s+\d{{1,2}}"
    r"|\d{4}-\d{2}-\d{2}"
)
_TRAILING = re.compile(rf"^(?P<title>.*\S)\s+(?P<phrase>{PHRASE})$", re.IGNORECASE)


def parse_due(text: str, today: date | None = None) -> date | None:
    today = today or date.today()
    s = text.strip().lower()
    if s == "today":
        return today
    if s in ("tomorrow", "tmrw"):
        return today + timedelta(days=1)
    if m := re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None
    if m := re.fullmatch(r"in\s+(\d+)\s+(day|week)s?", s):
        return today + timedelta(days=int(m[1]) * (7 if m[2] == "week" else 1))
    if m := re.fullmatch(rf"(next\s+)?({_DAY_RE})", s):
        target = next(i for i, d in enumerate(_DAYS) if d.startswith(m[2][:3]))
        ahead = (target - today.weekday()) % 7 or 7  # strictly after today
        if m[1]:  # "next fri" = that weekday in the following Mon-Sun week
            ahead = (7 - today.weekday()) + target
        return today + timedelta(days=ahead)
    if m := re.fullmatch(rf"({_MONTH_RE})\s+(\d{{1,2}})", s):
        month = _MONTHS.index(m[1][:3]) + 1
        try:
            d = date(today.year, month, int(m[2]))
            return d if d >= today else date(today.year + 1, month, int(m[2]))
        except ValueError:
            return None
    return None


def split_due(title: str, today: date | None = None) -> tuple[str, date | None]:
    """'Buy paint tomorrow' -> ('Buy paint', <tomorrow>). Leaves the title alone otherwise."""
    m = _TRAILING.match(title.strip())
    if m and (due := parse_due(m["phrase"], today)) is not None:
        return m["title"], due
    return title.strip(), None
