# 0018. Hide any card, revived from its own board -- replaces Review's per-card exclude

- Status: accepted
- Date: 2026-09-25
- Departs from standard: none

## Context

Review mode (ADR 0016) shipped with its own per-card exclusion mechanism: "just today" or
"always," managed from a "Excluded from Review" list in Settings. The owner asked for something
more general: hide a card the same way a board can be hidden from the sidebar or a list can be
hidden from a board, everywhere a card shows up, revived from the eye icon on the board/tasklist it
lives on -- and for this to fully replace Review's exclude, not sit alongside it.

## Decision

- **One boolean, `Card.hidden`, not the old today/always scoping.** List-hiding and board-hiding
  are both plain on/off, revived whenever from their own eye menu -- no timer. Matching that shape
  (confirmed with the owner rather than assumed, since "keep a same-day auto-expiring option too"
  was a real alternative) keeps hide/reveal a single mental model across boards, lists and cards
  instead of cards alone having a second, temporal mode.
- **Hides everywhere, not just its own board.** A hidden card drops out of every card-listing view:
  its board (`view_columns`), Scheduled/Today's due section/Review's upcoming (`scheduled_cards`),
  created-today (`created_on`), tag counts and cards-with-tag, Search (`search`), and Today/
  Logbook/Review's completed sections and Metrics (all built on `logbook()`, which now drops a
  hidden card's history too -- see below). This was the one genuinely ambiguous call in the
  request ("similar to hiding boards," which is sidebar-only) and was confirmed explicitly rather
  than assumed, since it changes the shape of the feature substantially either way.
- **`all_cards()` stays a raw, unfiltered feed on purpose.** Every real "view" consumer
  (`scheduled_cards`, `created_on`, `cards_with_tag`, `tag_counts`, `search`, and the two direct
  `all_cards()` call sites in routes.py) filters `not c.hidden` itself, rather than baking the
  filter into `all_cards()` centrally. `logbook()`'s fold-in step needs the *unfiltered* list to
  know which cards are currently hidden in the first place (so it can drop their history) -- if
  `all_cards()` already excluded them, that information would be unrecoverable from inside
  `logbook()`. Same reasoning as `list_cards()` staying raw for `cards_by_column`/exports.
- **A hidden card's completion history drops out of the Logbook too**, built from the same
  `all_cards()` pass `logbook()` already does for its fold-in step (no second query) -- "hidden"
  is meant to read as "not anywhere," including in a look-back report, not just "not on its board
  right now."
- **Quick, always-visible hide button on every row** (`.card-hide-btn`, one shared class/handler
  across `_card.html`, `_card_row.html`, `_logbook_row.html`, `_review_row.html`) -- not tucked
  into the edit dialog like Star (ADR 0016). Boards are hidden via a quick per-row button
  (`.hide-btn`, hover-revealed), which is the shape the request pointed at explicitly ("similar to
  how we are hiding boards"). Cards' own button is *not* hover-revealed, though, unlike the board
  one: this app installs to a phone home screen, and a hover-only control is unreachable on touch
  (the existing `.del` and edit-pencil buttons on a card are already always-visible for the same
  reason) -- one-directional, matching the × delete button beside it: reviving happens only from
  the board's own eye menu, not by clicking it again.
- **Revival lives on the card's own board/tasklist, in a new "Hidden cards" eye menu**
  (`_board_title.html`), mirroring the existing "hide lists" eye menu almost exactly -- own trigger
  button, own badge count, one row per hidden card with a "Show" button. Available on *both* board
  kinds (the lists one is kanban-only, since a tasks board has no lists to hide, but its cards can
  still be hidden one at a time). Settings does **not** get a management list for this (unlike the
  old Excluded-from-Review one it replaces) -- the board itself is the natural, already-established
  place a hidden *thing* on it gets managed, matching lists and unlike the old exclude, which had
  nowhere else to live since Review itself has no natural "per its own board" home.
- **A third `.eye-menu-wrap` on the same board page** (list-hide, card-hide, and the sidebar's own
  board-hide elsewhere) repeats a lesson already in AGENTS.md (trap 17): the shared
  `.eye-menu`/`.eye-row`/`data-eye-toggle` classes are deliberately generic and reused as-is (the
  open/close JS doesn't care what's inside), but anything that needs to tell two instances apart --
  a test locator, a future selector -- needs its own scope. Each wrapper here carries a second,
  purely-for-scoping class (`.list-eye-menu-wrap` / `.card-eye-menu-wrap`) alongside the shared
  ones, and each trigger button has its own distinct accessible name ("Show or hide lists" vs.
  "Show or hide cards").

## Consequences

- `standup.py`'s (now `review.py`'s) `excluded_ids()` and the whole `standup_exclusions`/
  `review_exclusions` storage key, `Store.exclude_from_review`/`include_in_review`, the
  `/review/exclude`/`/review/include` routes, `review.js`, and Settings' "Excluded from Review"
  section are all deleted, not deprecated -- confirmed the live instance had never actually stored
  an exclusion (checked `.trellis.yml` before deleting the feature), so nothing needed a migration.
- Unit tests cover `set_card_hidden`, `hidden_cards`, and hidden-card filtering in `view_columns`,
  `scheduled_cards`/`created_on`/`search`, and `logbook()`'s history-drops-out behavior. Route
  tests cover the hide/reveal round trip and confirm a hidden card actually disappears from every
  page (board, Today, Scheduled, Logbook, Review, Search) in one pass. One e2e test hides a card
  from a Review row and revives it from its board's new eye menu, exercising the full cross-page
  loop, not just the two ends of it in isolation.
