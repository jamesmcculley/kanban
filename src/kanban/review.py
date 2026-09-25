"""Pure logic for Review mode: which cards a "today" or permanent exclusion actually hides right
now, and clamping the free-text look-back/look-forward day counts. No I/O, no Flask.
"""

from __future__ import annotations

MAX_DAYS = 3650  # ~10 years -- a ceiling against a typo like "99999999", not a real limit


def excluded_ids(exclusions: list[dict], today: str) -> set[str]:
    """Card ids excluded from a report generated on `today` (an ISO date) -- a permanent exclusion
    (`until` is None/missing) always applies; a "just today" one (`until` is a date) only applies
    on that exact day, so it quietly stops hiding anything once the day has passed."""
    return {e["card"] for e in exclusions if not e.get("until") or e["until"] == today}


def clamp_days(raw: str, default: int) -> int:
    """A free-text field, not a dropdown -- 0 is a real, meaningful value ("don't show anything
    looking that direction"), so only a missing or unparseable value falls back to the default."""
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(0, min(n, MAX_DAYS))
