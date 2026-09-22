# 0006. Archive/unarchive a board, separately from Trash

- Status: accepted
- Date: 2026-09-22
- Departs from standard: none

## Context

Trash already exists for "I don't want this anymore, but let me undo it" — a short-lived safety net
before permanent deletion. There was no way to say "I'm not using this board right now, but I'm not
done with it" without either leaving it cluttering the sidebar forever or trashing it (which reads,
and behaves, as intent to delete).

## Decision

- `Board.archived: bool`, written to `board.md` only when `True` (same minimal-write pattern as
  every other optional board field). Archiving is a pure visibility toggle: a board's area,
  position, rules, settings and cards are untouched, and it's still reachable directly at its own
  URL — it just doesn't show up where you'd browse to it.
- Left out of, specifically: the sidebar (`Store.sidebar()`), the move-to/quick-capture board
  pickers (`nav()`'s `card_boards`), and everywhere `all_cards()` feeds — Scheduled, tag counts,
  cards-with-tag — plus `search()`. Deliberately *not* filtered out of: `list_boards()` itself, area
  management (`areas()`/`apply_layout()`/etc.), Trash's own board bookkeeping, the health check, or
  `logbook.py`'s "is this board still live" check — all of those need to see every board regardless
  of archived state to stay correct.
- A dedicated `/archived` page (list + Unarchive, styled like Trash's own list) rather than folding
  it into Settings: archived boards are something you come back to occasionally to restore, the same
  shape of task Trash already exists for, not a configuration surface. Linked from the sidebar's
  floating footer pill next to Trash, not a top-level nav item — one more icon there is free
  (see 0005's neighbour, the sidebar-overlap fix landed the same day) where one more permanent
  top-of-sidebar link would have added back exactly the clutter this session spent most of its time
  removing.
- No confirmation step on archiving (unlike delete's two-click confirm): it's fully reversible and
  changes nothing about the board's data, so treating it like a destructive action would be dishonest
  about the risk.

## Consequences

- A board's own page shows an "Archived" chip plus an Unarchive button in place of the Archive
  button when `board.archived` is true — the only UI surface that needed a branch for this; nothing
  about card rendering, rules, or per-board settings needed to know about board-level archiving at
  all, which is the intended payoff of keeping it a pure visibility filter over already-existing
  data rather than a new lifecycle state cards or other subsystems have to reason about.
