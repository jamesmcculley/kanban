# 0007. Board sort order, pinning, and full sidebar section visibility

- Status: accepted
- Date: 2026-09-23
- Departs from standard: none

## Context

Manual drag-to-reorder for boards already existed. The owner asked for alphabetical, recently-updated
and recently-created sort as alternatives, and — starting from "let me hide the tags section" —
generalized to wanting every sidebar section individually show/hideable, explicitly excepting the
floating toolbar ("that would break everything if that got hidden"). Mid-turn, also asked for a way
to pin a board so it stays on top regardless of whatever sort mode is active; a follow-up round added
the logo to the hideable list (missed the first time), a third sidebar size ("skinny", between
regular and fully hidden), and a way to resize the sidebar by dragging or typing a number.

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

- **The sidebar has three sizes, cycled by one button: Regular → Skinny → Hidden → Regular.** Same
  button both places (the in-sidebar toggle and the "show sidebar" rail that only appears at
  Hidden) — the rail lands on Regular directly not because it's special-cased, but because Hidden is
  the last step before the cycle wraps, so clicking it from Hidden always goes to Regular. Skinny is
  a fixed 72px rail: search, area labels, drag handles, the pin button and anything tag/text-heavy
  are hidden outright regardless of the "show in sidebar" choices (those are about what fits at
  Regular width, not a promise everything fits in 72px), and board/nav titles ellipsis-truncate to a
  letter or two with the native `title=""` tooltip carrying the rest.
- **Sidebar width is `localStorage`, like sort mode and section visibility** — a `--sidebar-width`
  CSS custom property, set by a drag handle on the sidebar's own right edge or a number field in
  Settings (`sidebar.js`'s `SidebarWidth`), read by the same pre-paint script that already applies
  theme/width/hide state before first paint. Both controls write the same key, so dragging on any
  page is what the Settings field shows next time it's opened — not live cross-tab sync, just
  "read fresh each time you open Settings," which is enough for a single-user personal app. Only
  applies at Regular; Skinny's 72px is fixed and the handle is hidden there and at Hidden.
- **A visible X (top-right) on every backdrop dialog** (Keyboard shortcuts, the card edit dialog) —
  both already closed via outside-click and Escape, but neither had a discoverable on-screen affordance.
  Settings gets one too, even though it's a real page with its own URL, not a modal: the owner named
  it in the same breath as "keyboard shortcuts," and a small `history.back()` link (falling back to
  home if there's no history to go back to) costs nothing and matches the same "always an obvious way
  out" expectation. Not applied to Trash, Archived boards, Search or other pages that weren't named —
  those already have sidebar links back, and adding it everywhere unasked would be exactly the kind
  of scope creep this session has otherwise been trying to remove, not add.

## Consequences

- Sort mode and section visibility never touch `.trellis.yml` or any board file — nothing here shows
  up in `git diff`-style change tracking of the data directory, and two people sharing the same LAN
  instance can have completely different sidebars without stepping on each other.
- A pre-existing, unrelated flaky e2e test (`test_drag_card_onto_sidebar_board_moves_it_with_undo`)
  surfaced repeatedly during this work's test runs, always passing in isolation — a real but
  separate issue (a timing race between two drag-handling code paths), not something this change
  caused or fixed. Left as a known flake, not chased down here.
- Skinny mode's first pass hid the pin button with the same hover-only `opacity` used everywhere
  else, which still reserves its layout space — at 64px that space was most of the row, and board
  titles rendered nothing at all (not even a truncated letter), making a board look like it had
  disappeared from the sidebar. Fixed with `display: none` and the width bumped to 72px; see AGENTS.md
  trap 16.
