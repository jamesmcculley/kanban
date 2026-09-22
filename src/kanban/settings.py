"""Settings and their resolution (pure: no I/O, no framework).

Global settings apply to every board; a board overrides only the keys it sets. A key a board does
not set is "inherited". Values are validated here so the storage layer only ever sees clean data.
"""

from __future__ import annotations

DEFAULT_COLUMNS = ["Todo", "Doing", "Done"]
POSITIONS = ("top", "bottom")
MAX_LISTS = 12

DEFAULTS = {
    "new_card_position": "top",      # where a newly added card goes in its list
    "hide_done": False,              # hide completed cards from the lists (they stay in the Logbook)
    "auto_hide_done_days": 0,        # hide a completed card this many days after completion; 0 = never
    "inherit_global_rules": True,    # boards only: also run the global rules
    "hide_list_titles": False,       # display only: declutter a board you already know by heart
    "hide_board_title": False,
    "hide_card_counts": False,
}
_BOOL_KEYS = ("hide_done", "inherit_global_rules", "hide_list_titles", "hide_board_title",
              "hide_card_counts")
BOARD_KEYS = tuple(DEFAULTS)
GLOBAL_KEYS = ("new_card_position", "hide_done", "auto_hide_done_days", "default_columns",
              "hide_list_titles", "hide_board_title", "hide_card_counts")


def _bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return None


def _list_names(value) -> list[str]:
    parts = value.replace("\n", ",").split(",") if isinstance(value, str) else list(value or [])
    names: list[str] = []
    for part in parts:
        name = " ".join(str(part).split())
        if name and name.lower() not in (n.lower() for n in names):
            names.append(name)
    return names


def clean(values: dict, keys: tuple[str, ...]) -> dict:
    """Validate `values`, keeping only `keys`. An empty value means "not set" and is dropped, which
    for a board means inherit. Raises ValueError with a message fit to show the user."""
    out: dict = {}
    for key in keys:
        if key not in values or values[key] in (None, ""):
            continue
        raw = values[key]
        if key == "new_card_position":
            if raw not in POSITIONS:
                raise ValueError("New cards go at the top or the bottom of a list")
            out[key] = raw
        elif key in _BOOL_KEYS:
            flag = _bool(raw)
            if flag is None:
                raise ValueError(f"{key.replace('_', ' ')} must be on or off")
            out[key] = flag
        elif key == "auto_hide_done_days":
            try:
                days = int(raw)
            except (TypeError, ValueError):
                raise ValueError("Days must be a whole number") from None
            if not 0 <= days <= 365:
                raise ValueError("Days must be between 0 and 365")
            out[key] = days
        elif key == "default_columns":
            names = _list_names(raw)
            if not names:
                raise ValueError("A new board needs at least one list")
            if len(names) > MAX_LISTS:
                raise ValueError(f"At most {MAX_LISTS} lists")
            out[key] = names
    return out


def resolve(global_settings: dict, board_settings: dict | None = None) -> dict:
    """Built-in defaults, then global, then the board's own overrides."""
    merged = {**DEFAULTS, "default_columns": list(DEFAULT_COLUMNS)}
    merged.update({k: v for k, v in global_settings.items() if k in GLOBAL_KEYS})
    merged.update({k: v for k, v in (board_settings or {}).items() if k in BOARD_KEYS})
    return merged
