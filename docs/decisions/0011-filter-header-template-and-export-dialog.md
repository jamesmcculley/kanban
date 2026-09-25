# 0011. One filter-icon header layout for every page that has one; a granular export dialog

- Status: accepted
- Date: 2026-09-24
- Departs from standard: none

## Context

Today's view put its filter icon in the page header, right next to the "Today" heading; Scheduled,
Logbook and Metrics instead put the whole date-filter bar in its own row *below* the header. The
owner asked to make Today's layout the template everywhere. Separately: Logbook's and Metrics'
"Export CSV" was a plain text link that downloaded the current date range unconditionally — the
owner wanted it as an icon next to the filter icon (no label), opening a pop-out with real options
(text search, tags, "basically anything a card/task could contain"), not just a direct download.

## Decision

- **`_date_filter.html`'s trigger button now lives directly in the caller's `<header class=
  "page-head">`, right after `<h1>`**, not wrapped in its own full-width `.filter-bar` row below
  the header. The popover itself is unchanged (`position: absolute`, floats below-right of the
  button) — only where the *trigger* sits in the page moved. Applied to `agenda.html` (Scheduled),
  `logbook.html` and `metrics.html`; `today.html` already did this and didn't need to change.
- **Export is now an icon-only button (`aria-label="Export activity"`) next to the filter icon**,
  opening `_export_dialog.html` into `#modal` (same `hx-get`/`#modal` pattern as the card-edit
  dialog) instead of linking straight to a CSV. The dialog is a plain GET form pointed at
  `/export/activity.csv`: submitting it *is* the download (matches the date filter's own "Apply"
  form), so no JavaScript was needed to make a file actually download.
- **The export dialog's fields — title text, tags, priority, board — are the same "nothing
  checked/typed = no narrowing, checking narrows" convention the per-board filter (`filter.js`)
  already established**, not a new mini-language. `Store.logbook()`'s events gained `tags` and
  `priority` (`logbook.py`'s `_event`, written going forward only) so an export can actually be
  narrowed by them; a new pure function, `metrics.filter_events`, applies all four narrowings
  (AND'd together) to an already date-filtered event list. Old log entries — logged before this
  shipped — simply never match a tag or priority filter, the same way a card with neither set
  wouldn't; the dialog says so.
- **Scope call: "expand this granularity to any filters throughout the app" is answered by having
  three consistently-granular surfaces — the per-board filter, this export dialog, and Advanced
  Search (a separate, following change) — not by bolting the same four fields onto Today's,
  Scheduled's and Logbook's date-only popovers too.** Those three date popovers stay date-only.
  Duplicating a text/tags/priority/board fieldset into three more small popovers would be more
  surface area with the same capability Advanced Search already covers app-wide (and covers
  *better*, since it isn't limited to one page's already-narrowed list) — more UI to maintain for a
  worse version of what Advanced Search does.

## Consequences

- `metrics.to_csv()`'s column set changed (`priority`, `tags` added before `repeating`) — a visible
  change to anyone already scripting against the old CSV shape, judged acceptable since this
  feature is new enough (shipped the day before) that nothing downstream depends on the old shape.
- `.filter-bar`'s CSS rule is gone (no longer anything wraps the trigger in its own row); `.date-
  filter-panel`/`.filter-panel` and friends are untouched.
- `tests/test_metrics.py` gained direct unit coverage for `filter_events` (text/tags/priority/board,
  individually and combined with AND); `tests/test_features.py` covers the same narrowing through
  the actual `/export/activity.csv` route.

**Amendment (a later round): Metrics itself gained the same narrowing, not just its export.** The
scope call above ("three surfaces, not five popovers") was about *not* duplicating text/tags/
priority/board onto Today/Scheduled/Logbook's plain date filters — Metrics asking for it directly
is a different request, not a re-litigation of that call, and `metrics.filter_events` was already
built and tested for exactly this shape. Its own filter icon (`.metrics-filter-wrap`, a fourth
distinct popover class alongside `.filter-wrap`/`.date-filter-wrap`/`.search-filter-wrap` — Metrics
already has the date filter's own popover on the same page, so it needed its own for the same
reason those three stayed apart) narrows the totals and both breakdowns; the Export link on a
filtered Metrics page carries the same criteria into the export dialog, so exporting what you're
already looking at doesn't mean re-entering the filter a second time.
