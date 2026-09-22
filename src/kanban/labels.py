"""Board-scoped labels: a small, named, recognisable-colour set per board, Trello-style (pure: no I/O).

Distinct from tags (#free-text, shared across every board): a label is `{id, name, color}`, the
color is one of a fixed named palette (so it reads consistently and meets contrast everywhere,
never an arbitrary user hex), and a card references labels it has by id, not by name, so renaming
or recolouring a label doesn't touch a single card file.
"""

from __future__ import annotations

import uuid

# name -> (fill, text). Text is whichever of black/white reads best on the fill (checked; every
# pair is >= 4.5:1). A 1px border is added in CSS so a light fill still reads on a light card.
COLORS = {
    "green": ("#4bae4f", "#000000"),
    "yellow": ("#e0b400", "#000000"),
    "orange": ("#e08a2a", "#000000"),
    "red": ("#e5484d", "#000000"),
    "purple": ("#8a5cd6", "#ffffff"),
    "blue": ("#3b82f6", "#000000"),
    "sky": ("#0ea5c4", "#000000"),
    "pink": ("#e0629e", "#000000"),
    "lime": ("#84b917", "#000000"),
    "grey": ("#78808c", "#000000"),
}
MAX_LABELS = 30


def clean_label(raw: dict, others: list[dict], label_id: str | None = None) -> dict:
    """Validate a label {name, color}. `others` are the board's existing labels (self excluded)."""
    name = " ".join(str(raw.get("name", "")).split())
    if not name:
        raise ValueError("give the label a name")
    if name.lower() in (o["name"].lower() for o in others):
        raise ValueError(f"a label named {name!r} already exists")
    color = raw.get("color", "")
    if color not in COLORS:
        raise ValueError("choose one of the label colours")
    return {"id": label_id or uuid.uuid4().hex[:8], "name": name, "color": color}
