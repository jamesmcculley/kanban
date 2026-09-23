# 0009. Per-board sidebar visibility, inline editing from Scheduled/Logbook, Metrics, activity export

- Status: accepted
- Date: 2026-09-23
- Departs from standard: none

## Context

A follow-up round on top of ADR 0007's sidebar customization: the owner asked to hide individual
boards from the sidebar (not just whole sections), for the Logbook's text-only "Edit date" action
(and Scheduled's cards) to open a real edit dialog instead, and — "it could be fun" — for a Metrics
view of what's been completed over a period, plus a CSV export of that activity, all/date-range.

## Decision

- **Hiding one board from the sidebar is a personal, per-device preference (`localStorage`), same
  reasoning as ADR 0007's sort order and section visibility** — not a board property like archived
  or pinned, since it's about *this device's* clutter, not something that should be the same for
  everyone sharing the instance. A new eye icon next to the "Boards" heading (same look as the
  existing per-board "show/hide lists" panel) lists every board with a checkbox; unchecking one
  hides its `.board-row` immediately and persists.
  - Unlike section visibility, whose keys are a small fixed set (`data-sidebar-hide~="tags"` etc.),
    a board's slug is arbitrary — there's no way to write a static CSS rule ahead of time for a
    value you don't know yet. Pre-paint hiding (so there's no flash of a board that's about to
    disappear) instead injects a `<style>` tag with one generated rule per hidden slug, id'd
    (`#hidden-boards-css`) so `sidebar.js`'s `HiddenBoards.set()` can replace its contents later
    without a reload — the same "written pre-paint by `_theme_boot.html`, kept in sync afterward by
    `sidebar.js`" split already used for `data-sidebar-hide`.
- **Scheduled's cards and every live Logbook entry get an edit (pencil) icon button that opens the
  same card-edit dialog (`_edit.html`) as clicking a card's title on its own board — not a second,
  parallel edit form.** The Logbook's old inline "Edit date" editor only ever touched the completion
  timestamp; the full dialog does everything it did and also title, dates, tags, priority, labels,
  notes — "all the fields," as asked, for free, since it's the same dialog. The dialog's own
  completed-at field already only shows for a done, non-repeating card, so it needs no extra gating
  for the entries that don't have one (repeating-card log lines, mostly).
  - Neither Scheduled nor the Logbook has a `.card[data-id]` element for the dialog's usual
    in-place swap to land on (Scheduled's `.row` looks nothing like a board card, and an edited due
    date can move a Scheduled card to a different day-group entirely; the Logbook has no live card
    markup at all). `_edit.html` now takes a `standalone` flag (set when opened via
    `?standalone=1`, which both pages' edit buttons pass) that swaps its save behaviour from
    "patch the card in place" to "reload the page" — the same fallback the completed-at-save button
    already had for exactly this reason, now applied to the whole form.
- **A `/metrics` page**: a total for the current date range (reusing the same filter/presets/saved-
  filter UI as Scheduled and the Logbook — one more `_date_filter.html` consumer, not a new
  mechanism) plus two breakdowns — busiest board, and busiest day of the week — as plain CSS bar
  charts (a `<div>` whose width is a percentage; no charting library, per the no-third-party-
  runtime-requests boundary). Kept to two breakdowns, not a full analytics suite: enough to be
  genuinely interesting to glance at without turning into its own subsystem.
  - `Store.logbook()` gained `limit=None` (its `limit=500` default, used by the Logbook page itself,
    would silently under-count a busy "all time" Metrics query or a large CSV export). Aggregation
    itself lives in a new pure module, `metrics.py` (`by_board`, `by_weekday`, `to_csv`), joining
    the boundary list in `AGENTS.md` — the same reasoning as `csvimport.py`: not Flask, not I/O,
    independently testable.
- **CSV export** (`/export/activity.csv?from=&to=`) reuses that same `logbook(limit=None, ...)` call
  and `metrics.to_csv()`. Reachable from both Metrics and the Logbook's header (both already resolve
  a date range the same way), not a separate page. "Export all" is just the export link with no
  range applied — the existing "All" preset already means exactly that, nothing new needed.
- **"Whenever possible, actions should be icons" was applied to what was actually named** (the
  Logbook's "Edit date" text button, now a pencil icon) and to the two new edit buttons this round
  added (Scheduled, Logbook) — not as a prompt to re-skin every text button in the app (`Cancel`,
  `Save`, `Show all`/`Hide all`, `Restore default`, etc.), which are primary form/panel actions
  where a label reads better than an icon and where nothing was asked. Same scope discipline as
  ADR 0007's X-buttons decision.

## Consequences

- Reusing the existing "reveal a checklist panel" look (`.eye-menu-wrap`, `[data-eye-toggle]`,
  `.eye-menu`, `.eye-row`, `.icon-badge`) for the new sidebar panel was right for the shared JS (one
  generic open/close/outside-click handler in `ui.js` needs no changes to serve both) but broke
  several existing Playwright locators that queried those classes unscoped, now that a kanban board
  page can show two such panels at once. Fixed by scoping each test to its own panel's container
  and giving the new badge its own class. See `AGENTS.md` trap 17 — same shape as trap 9's
  `.filter-wrap` collision from the original per-board filter work.
- `tests/test_features.py`'s new 510-entry Logbook-limit test writes the `.trellis-log.jsonl` file
  directly rather than calling `add_card`/`complete_card` 510 times — the same behaviour, ~100x
  faster, since the test only cares what `logbook()` does with an already-full log file.

**Amendment (same day, after real use):** Metrics moved from a sidebar nav link to a toolbar icon
in `.side-foot`, next to Trash/Archived/Settings — the owner's feedback was that it read as a
"page in the list of pages" when it's really an app-level view, same category as Settings, not a
Today/Scheduled/Logbook peer. It keeps its `g m` shortcut (the `data-go` lookup matches any element
in `.sidebar`, not just `nav a`) and, since the toolbar always stays put, it's no longer one of the
"show/hide in the sidebar" choices either — same as Trash/Archived/Settings already weren't.

Also from that feedback: the checkbox-only "hide boards" panel was hard to read at a glance (a
plain, unlabelled checkbox doesn't say "this is currently hidden" the way a strikethrough does) and
required opening a panel even to hide the one board you're already looking at. Fixed two ways: (1)
`.eye-row:has(input:not(:checked))` dims and strikes through a hidden row's label — cheap, and
fixes the same legibility gap in the older per-board "hide lists" panel for free, since both share
the `.eye-row` class. (2) Each board row gained its own hover-revealed hide button (`.hide-btn`,
same reveal-on-hover pattern as the pin button, same row). The panel is still there for reviewing
everything that's hidden and restoring it — just no longer the only way in.
