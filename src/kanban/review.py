"""Pure logic for Review mode: clamping the free-text look-back/look-forward day counts. No I/O,
no Flask.

(Review mode used to have its own per-card exclusion mechanism here -- see ADR 0016's amendment.
It was replaced by the generic Card.hidden flag, which every card-listing view honors, not just
this one; see store.py's set_card_hidden and ADR 0017.)
"""

from __future__ import annotations

MAX_DAYS = 3650  # ~10 years -- a ceiling against a typo like "99999999", not a real limit


def clamp_days(raw: str, default: int) -> int:
    """A free-text field, not a dropdown -- 0 is a real, meaningful value ("don't show anything
    looking that direction"), so only a missing or unparseable value falls back to the default."""
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(0, min(n, MAX_DAYS))
