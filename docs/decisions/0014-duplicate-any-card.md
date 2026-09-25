# 0014. Duplicate any card, from anywhere

- Status: accepted
- Date: 2026-09-24
- Departs from standard: none

## Context

The owner asked to "allow any card to be duplicated from anywhere" — not just from its own board.

## Decision

- **The Duplicate button lives in the shared card-edit dialog (`_edit.html`), not on the card face
  or in each page's own row markup.** That dialog is already the one place every page in the app
  opens a card from — board, tasks board, Scheduled, Logbook, Today, Search — so putting it there
  once *is* "from anywhere," with no per-page wiring. Same reasoning as `standalone` mode (ADR
  0011): one shared surface beats duplicating (no pun intended) the same button into six templates.
- **`Store.duplicate_card` copies everything meaningful — tags, labels still defined on the board,
  priority, start/due, repeat, notes — except title (` (copy)` appended, same convention as
  `duplicate_search`) and done state, which always starts fresh.** A duplicate is "another one of
  these," not "another copy of something I already finished"; carrying `done`/`completed` over
  would make a freshly duplicated card show up already checked off, which is never what duplicating
  is for. "Added" rules run on the copy, same as any other new card.
- **The copy lands immediately after the original in the same list** (built at the end via the
  existing `add_card`-style append, then repositioned with the existing `_move` helper) — the
  obvious place to look for it, and reuses machinery that already handles reindexing correctly
  rather than writing new positioning logic.
- **Undo is just `boards.delete_card`, the same endpoint deleting any other card already uses** —
  a duplicate is a card like any other the moment it exists, so "undo creating it" is exactly
  "delete it," no new undo mechanism needed.

## Consequences

- `tests/test_store.py` covers field-copying, the done-state reset, label filtering (only labels
  still defined on the board survive, same rule `add_card` already follows) and the not-found path;
  `tests/test_routes.py` and two new e2e tests cover the route and the button reachable from both a
  board (in-place) and a standalone context (Today).
- Found writing the e2e tests: the button's `title="Duplicate this card"` isn't its accessible
  name once it also has visible text ("Duplicate") — the text wins. See `AGENTS.md` trap 21.

**Amendment (a later round): duplicate a whole board too.** `Store.duplicate_board` follows the
same shape but a deliberately *different* rule for what "fresh" means:

- **Every card is copied exactly as it is, done state included** — duplicating a card is "another
  one of these" (fresh makes sense), but duplicating a *board* is "a snapshot of this board right
  now," where a done card silently becoming un-done on the copy would be actively wrong, not just
  unhelpful. Title still gets ` (copy)` appended (the board's, not each card's — cards keep their
  own titles unchanged), same convention either way.
- **Structure, settings, rules and label definitions all copy too** (columns, hidden-list state,
  area, board-level settings overrides, rules, labels) — a board's automation and layout are part
  of what makes it *that board*; a duplicate missing its rules would surprise the owner the first
  time a card doesn't do what the original board's did.
- **Starts unpinned and unarchived regardless of the original** — same reasoning as a duplicated
  search starting unpinned (ADR 0012): a duplicate is meant to be immediately useful, not to
  silently inherit state that was about the *original's* place in the sidebar, not the copy's.
- **No undo toast** (unlike duplicating a card) — the route redirects straight to the new board
  (`data-after="navigate"`, a new case added to the shared `[data-post]` handler in `ui.js`,
  mirroring the FAB's own "create, then `location.href` to it" flow for new boards), and a
  redirect has no JSON body to carry toast data in. The new board's own "Delete board" button,
  right there once you land on it, is itself undoable if the copy turns out unwanted — good enough
  without inventing a way to attach a toast to a redirect.
- `_unique_slug` was pulled out of `create_board` (it needed the identical "make a slug, disambiguate
  with -2, -3... if taken" logic) rather than copied a second time.
