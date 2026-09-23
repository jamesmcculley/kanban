# 0010. A Today view; per-device page-title visibility

- Status: accepted
- Date: 2026-09-23
- Departs from standard: none

## Context

Mid-way through wrapping up ADR 0009's round, the owner asked for a Today view: what's due or
overdue, what got completed today, and what got *created* today, in one place -- with the same
show/hide-each-section and edit-pencil treatment as the rest of this round, plus a way to hide the
big page heading on Today, Scheduled and the Logbook (the standing settings page already had a
spot for "this device only" preferences). A dedicated Today page existed once before and was
folded into Scheduled (2026-09-22); this isn't reverting that -- it's a new, richer view that
Scheduled's own date-range filter can't express, since "completed today" and "created today" aren't
about a card's due/start date at all.

## Decision

- **Cards gained `created`** (`Card.created`, an ISO timestamp set once by `add_card` and never
  touched again -- same shape as `Board.created` from ADR 0007, but stored in the card's own
  frontmatter rather than derived from a file's mtime, since a card's mtime changes on every edit,
  not just its creation). A card saved before this shipped has no `created` key and simply never
  matches "created on X" -- there's no way to know when it was made, and treating "unknown" as
  "today" would be actively wrong. `Store.created_on(day)` is the query, newest first, living next
  to `scheduled_cards` and `search`.
- **`/today` reuses `scheduled_cards(date_to=today)` for due/overdue and `logbook(date_from=today,
  date_to=today)` for completed** -- no new query logic for either, just the existing ones called
  with today's date as the bound. Only "created today" needed something new.
- **Both this round's row-shapes were pulled out into shared macros** (`_card_row.html`'s
  `card_row`, `_logbook_row.html`'s `logbook_row`) instead of copy-pasting Scheduled's and the
  Logbook's row markup a second and third time -- Today needs the exact same "due" row shape
  Scheduled uses, and the exact same "completed" row shape the Logbook uses, edit pencil included
  for free since that's already baked into the macro. Scheduled and the Logbook were refactored to
  call the same macros, so there's exactly one place each row shape is defined, not three drifting
  copies.
- **Which of the three sections show is a Today-page popover (`today-hide`, localStorage), not a
  Settings checkbox list** -- unlike sort order or sidebar sections, this is "what do I want to see
  on Today right now," closer to the per-board filter than to a standing device preference. Applied
  pre-paint (`_theme_boot.html`, `data-today-hide` on `<html>`) the same way `data-sidebar-hide`
  is, since it's a small fixed key set (due/completed/created), not arbitrary values like the
  per-board hide in ADR 0009.
- **Page-title visibility (Today/Scheduled/Logbook) is a new Settings section, `page-title-hide`
  (localStorage), same pre-paint mechanism again** -- `h1[data-page="..."]` on each page's own
  heading, hidden via `data-page-title-hide~="..."`. A parallel, independent key set from sidebar
  section visibility: hiding "Today" from the *sidebar* (ADR 0009's `sidebar-hide`) and hiding the
  word "Today" at the *top of the Today page itself* are different questions with different
  answers, so they're deliberately not the same checkbox.

## Consequences

- Reusing macros meant Scheduled's and the Logbook's own row markup shrank to a one-line loop body;
  no behaviour changed for either page.
- A second thing named "Today" on the page (the sidebar's new nav link, alongside the Scheduled/
  Logbook date filter's existing "Today" preset chip) broke an existing Playwright locator that
  matched by accessible name without scoping to a container. Fixed by scoping it. See `AGENTS.md`
  trap 18.
- `tests/test_store.py`'s new `created_on` test simulates a pre-upgrade card (no `created` key) by
  editing its saved frontmatter directly, same pattern already used for the Logbook's own backfill
  test -- confirms old cards are silently excluded rather than mis-sorted into "today."

**Amendment (same day, after real use):** the owner asked why Today didn't get a count badge the
way Scheduled has. It should have from the start -- Today's due-or-overdue count is the exact same
query Scheduled's badge already uses (`nav()`'s `today_count`, `scheduled_cards(date_to=today)`),
so the Today link just needed its own copy of the same badge markup (`#today-view-badge`, alongside
Scheduled's `#today-badge`) reading the same variable. `_stats.html` (the fragment `sidebar.js`
re-fetches after every card change) renders both from the one value, so they never drift apart.
