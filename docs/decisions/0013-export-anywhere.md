# 0013. Export from a board, Scheduled and Today, not just Logbook/Metrics

- Status: accepted
- Date: 2026-09-24
- Departs from standard: none

## Context

ADR 0011 gave Logbook and Metrics a granular export dialog, but only for *completed activity*.
The owner asked for export "on anything — Today, individual boards, Scheduled" — real cards, not
just the completed-activity log.

## Decision

- **A new pure function, `csvimport.cards_to_csv`, exports `(board, card)` pairs in the exact
  column shape `parse_csv` already reads** (title, board, list, start, due, tags, priority, notes,
  done) — export, edit in a spreadsheet, re-import is a real round trip, not a one-way dump. This
  lives in `csvimport.py` (renamed in spirit, not on disk, to own both directions of the CSV <->
  card boundary) rather than next to `metrics.to_csv`, which exports a different shape (logbook
  *events*, not live cards) for a different purpose.
- **`search.refine` (ADR 0012) gained `q` (title text) and `lists` (column)**, so the one function
  now does all the narrowing every export dialog and Advanced Search need: text, tags, priority,
  board, list, status. A board's own export needed `lists`; Advanced Search's route still doesn't
  pass `q` to `refine` (it already filters text via `Store.search()`, which also searches notes —
  passing `q` again would wrongly exclude a note-only match).
- **One shared dialog template, `_cards_export_dialog.html`**, not three separate ones — the
  fields are mostly the same (text, tags, priority) and only three optional blocks differ:
  `boards` (Scheduled/Today: multi-board sources), `columns` (a single board: makes no sense
  cross-board), `show_status`/`show_sections`. Each route just decides which optional context to
  pass, the same "one template, conditional blocks" choice already made for the page-head filter
  layout in ADR 0011.
- **Today's export combines three different queries into one file with a leading `section`
  column** (`cards_to_csv`'s `sections` parameter) rather than three separate downloads — "due" and
  "created" are real, already-live `(board, card)` pairs; "completed" comes from Logbook events, so
  `_resolve_logged_cards` looks up each event's live card (skipping any whose board or card is
  gone) before it can be run through the same `refine`/`cards_to_csv` pipeline as the other two. A
  card appearing in more than one section (created and completed today, say) gets one row per
  section, not a merged/deduplicated row — each section's own filter and export options stay
  independently meaningful that way.
- **Board export defaults to every card on the board, not just what's currently visible** —
  `Store.list_cards`, unfiltered by the board's own hidden-lists or auto-hide-done settings; a
  board is (deliberately) the one export surface with no date range, since "the whole board, right
  now" is what "export this board" means until narrowed by its own dialog's fields.

## Consequences

- `routes.py` picked up a small `_card_boards()` helper (boards eligible to appear in a board
  picker), replacing three near-identical list comprehensions that had drifted into existence
  across earlier rounds (Advanced Search, the activity export dialog, and now these) — a drive-by
  cleanup, not a new decision.
- `tests/test_csvimport.py` covers `cards_to_csv` directly, including the round trip back through
  `parse_csv` and the `sections` column; `tests/test_search.py` covers the two new `refine`
  parameters; `tests/test_routes.py` and two new e2e tests cover each of the three new export
  surfaces end to end (a board narrowed by list, and that Scheduled/Today both expose the button).
