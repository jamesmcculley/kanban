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


def parse_iso_range(raw_from: str, raw_to: str) -> tuple[str | None, str | None]:
    """Validate a from/to pair of plain ISO dates (what an <input type=date> submits). Either
    side blank means open-ended. Used for Scheduled/Logbook date-range filters, not free text."""
    def one(raw: str) -> str | None:
        raw = (raw or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw).isoformat()
        except ValueError:
            raise ValueError("dates must be in YYYY-MM-DD form") from None
    d_from, d_to = one(raw_from), one(raw_to)
    if d_from and d_to and d_from > d_to:
        raise ValueError("the start of the range must be before the end")
    return d_from, d_to


def split_due(title: str, today: date | None = None) -> tuple[str, date | None]:
    """'Buy paint tomorrow' -> ('Buy paint', <tomorrow>). Leaves the title alone otherwise."""
    m = _TRAILING.match(title.strip())
    if m and (due := parse_due(m["phrase"], today)) is not None:
        return m["title"], due
    return title.strip(), None


# -- recurrence ---------------------------------------------------------------------------------
# Rules are stored as canonical text ("every monday", "every 2 weeks", "every weekday") so the
# card files stay human-readable and hand-editable.

REPEAT_PHRASE = (
    r"daily|weekly|monthly"
    rf"|every\s+(?:weekday|(?:{_DAY_RE})|(?:\d+\s+)?(?:day|week|month)s?)"
)
_TRAILING_REPEAT = re.compile(rf"^(?P<title>.*\S)\s+(?P<phrase>{REPEAT_PHRASE})$", re.IGNORECASE)


def _rule(text: str) -> tuple | None:
    s = re.sub(r"\s+", " ", text.strip().lower())
    if s in ("daily", "weekly", "monthly"):
        return ("interval", 1, {"daily": "day", "weekly": "week", "monthly": "month"}[s])
    if s == "every weekday":
        return ("weekdays",)
    if m := re.fullmatch(rf"every ({_DAY_RE})", s):
        return ("weekday", next(i for i, d in enumerate(_DAYS) if d.startswith(m[1][:3])))
    if m := re.fullmatch(r"every (?:(\d+) )?(day|week|month)s?", s):
        n = int(m[1] or 1)
        return ("interval", n, m[2]) if n >= 1 else None
    return None


def parse_repeat(text: str) -> str | None:
    """Normalise a repeat phrase ('daily', 'every 2 wks'...) or return None if unrecognised."""
    rule = _rule(text)
    if rule is None:
        return None
    if rule[0] == "weekdays":
        return "every weekday"
    if rule[0] == "weekday":
        return f"every {_DAYS[rule[1]]}"
    _, n, unit = rule
    return f"every {unit}" if n == 1 else f"every {n} {unit}s"


def split_repeat(title: str) -> tuple[str, str | None]:
    """'Water plants every monday' -> ('Water plants', 'every monday')."""
    m = _TRAILING_REPEAT.match(title.strip())
    if m and (rule := parse_repeat(m["phrase"])):
        return m["title"], rule
    return title.strip(), None


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):  # clamp: Jan 31 + 1 month -> Feb 28/29
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise AssertionError("unreachable")


def _weekday_on_or_after(d: date, ok) -> date:
    while not ok(d):
        d += timedelta(days=1)
    return d


def first_due(rule: str, today: date | None = None) -> date:
    """First occurrence for a brand-new repeating card: today if it fits, else the next match."""
    today = today or date.today()
    r = _rule(rule)
    if r is None:
        raise ValueError(rule)
    if r[0] == "weekday":
        return _weekday_on_or_after(today, lambda d: d.weekday() == r[1])
    if r[0] == "weekdays":
        return _weekday_on_or_after(today, lambda d: d.weekday() < 5)
    return today


def next_occurrence(rule: str, due: date | None, today: date | None = None) -> date:
    """The due date after completing a repeating card.

    Interval rules keep their fixed schedule (biweekly on Mondays stays on Mondays even if you
    finish late) and skip any occurrences already in the past. Weekday rules go to the next
    matching day after whichever is later, the old due date or today.
    """
    today = today or date.today()
    r = _rule(rule)
    if r is None:
        raise ValueError(rule)
    if r[0] in ("weekday", "weekdays"):
        base = max(due or today, today) + timedelta(days=1)
        if r[0] == "weekday":
            return _weekday_on_or_after(base, lambda d: d.weekday() == r[1])
        return _weekday_on_or_after(base, lambda d: d.weekday() < 5)
    _, n, unit = r
    start = due or today
    k = 1
    while True:
        cand = (_add_months(start, n * k) if unit == "month"
                else start + timedelta(days=n * k * (7 if unit == "week" else 1)))
        if cand > today:
            return cand
        k += 1
