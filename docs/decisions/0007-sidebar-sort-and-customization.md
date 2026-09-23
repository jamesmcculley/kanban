# 0007. Board sort order, pinning, and full sidebar section visibility

- Status: accepted
- Date: 2026-09-23
- Departs from standard: none

## Context

Manual drag-to-reorder for boards already existed. The owner asked for alphabetical, recently-updated
and recently-created sort as alternatives, and — starting from "let me hide the tags section" —
generalized to wanting every sidebar section individually show/hideable, explicitly excepting the
floating toolbar ("that would break everything if that got hidden"). Mid-turn, also asked for a way
to pin a board so it stays on top regardless of whatever sort mode is active.

## Decision

- **Sort order is a personal, per-device preference (`localStorage`), not a server setting.** The
  server's own board order — what dragging writes to `Board.position` — is the single source of
  truth and is never touched by picking Alphabetical/Recently updated/Recently created; those are a
  client-side re-sort of the already-rendered `.board-row` elements (`sidebar.js`'s `BoardSort`),
  applied on load and re-applied on every page (not persisted server-side). Switching back to Manual
  always shows the real order exactly as it was, with nothing to "undo." Manual-mode dragging stays
  wired up as before; the other three modes disable it (`Sortable` is simply never initialized on
  those containers), since dragging in a re-sorted view would just get overridden on the next load.
- **`Board` gained `created` (written once, in `create_board`, never touched again) and `updated`**
  (not stored — read from `board.md`'s own mtime). `Store._save()` (every card write) also touches
  `board.md`'s mtime, so "recently updated" reflects real activity in a board, not just board-level
  metadata changes (rename, settings, rules) — cheap (`Path.touch()`, no rewrite) versus the
  alternative of scanning every card's own mtime on every sidebar render.
- **Section visibility is also `localStorage`**, same reasoning as sort order and consistent with
  where theme/text-size/sidebar-collapsed already live: a personal viewing preference, not something
  that needs to be the same across devices or require a server round-trip to change. Applied
  pre-paint (`_theme_boot.html`, sets `data-sidebar-hide` on `<html>` before the sidebar itself
  renders) so there's no flash of a section that's about to disappear, the same technique already
  used for theme. Six independent toggles: search, Scheduled, Logbook, the whole boards+areas block,
  tags, and the theme-toggle pill — granular enough to be useful, not so granular (e.g. no per-area
  toggle) that the settings UI itself becomes clutter.
- **The floating `.side-foot` toolbar (Trash, Archived boards, Settings, Shortcuts, Collapse, Log
  out) is not one of the choices, deliberately** — it's the one thing guaranteed to stay reachable
  no matter how aggressively the rest of the sidebar is hidden, so there's always a way back into
  Settings to undo an over-enthusiastic hide. This was already true structurally (it's a
  `position: fixed` pill outside the sidebar's own flow, landed in the previous session's sidebar-
  overlap fix); this decision is what makes it *permanently* true rather than incidentally true.
- **`Board.pinned` is server-side, not `localStorage`, unlike sort mode and section visibility** —
  a pin is a property of the board itself (like archived, or its area), the same for whoever's
  looking at it, not a personal viewing preference. `Store.sidebar()` stable-sorts each group
  (unassigned, or an area's boards) by "pinned first," so Manual mode gets pinned-first for free
  from the server's own order; `BoardSort.apply()`'s client-side re-sort for the other three modes
  applies the identical pinned-first rule before its own alphabetical/updated/created comparison, so
  a pin wins regardless of sort mode, matching what was asked for exactly. Toggled from a small pin
  icon directly on each sidebar row (hover-revealed when unpinned, always shown — as a status
  indicator — once pinned), not from the board's own settings page: pinning is fundamentally about
  the sidebar, so that's where the control lives.

## Consequences

- Sort mode and section visibility never touch `.trellis.yml` or any board file — nothing here shows
  up in `git diff`-style change tracking of the data directory, and two people sharing the same LAN
  instance can have completely different sidebars without stepping on each other.
- A pre-existing, unrelated flaky e2e test (`test_drag_card_onto_sidebar_board_moves_it_with_undo`)
  surfaced twice during this work's test runs, always passing in isolation — a real but separate
  issue (a timing race between two drag-handling code paths), not something this change caused or
  fixed. Left as a known flake, not chased down here.
