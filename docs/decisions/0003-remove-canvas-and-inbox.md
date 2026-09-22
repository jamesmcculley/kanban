# 0003. Remove the canvas board and the pinned Inbox board

- Status: accepted
- Date: 2026-09-22
- Departs from standard: none

## Context

The canvas board kind (freeform notes, links, images, nested boards) shipped 2026-09-19. Checked
against the live data before removing it: zero canvas boards and zero nested boards existed on the
deployed instance, so there was nothing to migrate. The owner asked to remove it outright rather than
maintain a feature going unused.

The Inbox board (a pinned, specially-named kanban board created automatically for quick capture)
shipped 2026-09-20. It stood out as inconsistent with every other board: it couldn't be renamed,
reordered normally, or excluded from the sidebar's board list the way a real board could. The owner
called it "a bit out of place" while asking for capture to keep working.

## Decision

- Delete the canvas kind entirely: `canvas.py`, `canvas_routes.py`, their templates, `canvas.js`, and
  the `CanvasMixin`/`BOARD_KINDS` multi-kind plumbing in `Store`. `Board.kind` and `Board.parent`
  stay on the dataclass (a board could still theoretically nest, and old data with `kind: canvas`
  reads back as an empty-columns kanban board rather than crashing) but nothing sets either again.
- Quick capture (`c`) keeps working exactly as before, minus the special pinning: the fab's capture
  form now shows a board `<select>`, defaulting to the last board you captured into (`localStorage`,
  a per-device preference, not app data — consistent with 07), falling back to the board you're
  currently viewing, falling back to the first board. `/capture` requires an explicit `board` form
  field; there is no more `ensure_inbox()`/`inbox_count()`/`/inbox` route.
- A board created before this change that happens to be named "Inbox" is now an ordinary board.

## Consequences

- Two board kinds down to one; `sidebar()`'s `b.parent is None` filter and `trash_board()`'s
  child-reparenting logic are now dead code paths, kept because they cost nothing and stay correct if
  a hand-edited file ever sets `parent`.
- Capture takes one more click (choosing a board) the first time on a device, none after — the
  remembered choice covers the common case the pinned Inbox existed for.
- Found and fixed a real bug while re-testing bulk actions in a browser: the hidden-lists panel's
  "Hide all" fired one fetch per list via `Promise.all`, a set of concurrent read-modify-writes to the
  same `board.md` that silently clobbered each other. Fixed by awaiting them one at a time
  (AGENTS.md trap 6) — unrelated to this ADR's subject, but found in the same pass.
