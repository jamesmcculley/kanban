# 0015. Bulk actions on a board: select several cards, act on all of them

- Status: accepted
- Date: 2026-09-24
- Departs from standard: none

## Context

Acting on several cards at once meant doing each one individually — drag each one, or open each
one's edit dialog. The owner asked for bulk actions.

## Decision

- **Scoped to a board's own page (kanban and tasks) for this round, not Scheduled/Logbook/Today/
  Search too.** A board is where cards are already visually browsable and where the existing
  single-card endpoints (move, duplicate, delete) are already board-scoped; extending this to
  cross-board list views is a reasonable next step, not included here — same kind of scope call as
  ADR 0011's "three granular-filtering surfaces, not five."
- **No new server routes.** "Select cards" reveals a second checkbox per card (`.select-check`,
  next to the existing done-checkbox) and a floating bar with Move/Duplicate/Delete; each button
  loops over the selected ids and calls the *existing* single-card endpoint for each one, one
  request at a time — never `Promise.all` (AGENTS.md trap 6: concurrent writes to the same
  `board.md` silently clobber each other). Reusing proven endpoints instead of inventing bulk-
  specific ones means the bulk actions inherit their correctness (rules still run on a bulk
  duplicate, a bulk-deleted card still lands in Trash, not gone) for free.
- **Selection is client-side only, not persisted** — same category as sort order or section
  visibility (a personal, in-the-moment viewing state), except this one doesn't even survive a
  reload on purpose: turning "Select cards" back off, or reloading, clears it. There's no scenario
  where reopening the board with yesterday's selection still checked would be useful.
- **Bulk "complete" was deliberately left out.** The single-card complete endpoint *toggles* done
  state; looping it over a mixed selection (some done, some not) would un-complete the done ones,
  which is never what "bulk complete" means. Fixing that needs either a new set-not-toggle endpoint
  or client-side filtering by current state — judged not worth the added surface for this round,
  given Move/Duplicate/Delete already cover the actions with unambiguous semantics.
- **Bulk delete needed its own two-step confirm, not `ui.js`'s existing `[data-post]` one** — a
  `[data-post]` button posts to one fixed URL; a bulk action posts to a different URL per selected
  card, once each. Small and self-contained rather than generalizing the shared helper for one
  caller.
- **The bulk-delete button, and the others, got explicit `aria-label`s.** Found writing the e2e
  test: `aria-label` wins over text content for accessible-name purposes, and the confirm button's
  visible text *changes* on the first click (the "Click again" label gets appended) — without an
  `aria-label`, a locator that found the button before arming it couldn't find it again after.
  Went looking for the same gap elsewhere while in there: two pre-existing `data-confirm` buttons
  had the identical bug (Trash's "Empty trash", a saved search's "Delete" in Settings) — fixed
  both alongside the new one, not just documented as a trap for later.
- **A second, non-obvious CSS conflict**: `.selected` was already taken (`keys.js`'s single-card
  keyboard-navigation highlight). A selected-for-bulk-action card is styled with
  `:has(.select-check:checked)` instead of a second JS-toggled class, avoiding the collision
  without needing a new class at all.

## Consequences

- No new unit/route-level Python tests were needed beyond a markup-presence check — every action
  bulk.js drives is already covered by existing tests for the single-card endpoint it calls in a
  loop. Coverage for the feature itself (selecting, the bar showing/hiding, each action's actual
  effect, the two-step delete confirm) lives in four new e2e tests, since that's where the real
  risk is (client-side orchestration), not in the server.
