# 0012. Advanced Search, and saved searches pinnable to the sidebar

- Status: accepted
- Date: 2026-09-24
- Departs from standard: none

## Context

Following ADR 0011's export dialog, the owner asked for the same idea applied to Search: a way to
narrow by "any number of fields a card/task/board could contain" and combine them, plus the
ability to save a search, pin it to the sidebar, and rename/edit/duplicate/delete it.

## Decision

- **Advanced Search reuses the same header layout ADR 0011 established** — a filter icon next to
  the `<h1>` on `results.html`, opening a panel with tags/priority/board/status fields alongside
  the existing text query. Same "nothing set = no narrowing, multiple choices in one field are OR,
  multiple fields together are AND" convention as the per-board filter and the export dialog — a
  fourth surface using the one filtering vocabulary, not a new one.
- **A new pure module, `search.py` (`refine`)**, narrows `(board, card)` pairs the same shape
  `Store.search()` and `Store.all_cards()` already return — mirrors `metrics.filter_events` closely
  enough that the two could have been one module, but they narrow different data shapes (logbook
  event dicts vs. live `(Board, Card)` pairs) for a different purpose, so they stayed separate.
- **An empty text box with an advanced field set still searches** (starting from `all_cards()`
  instead of `Store.search()`, which returns nothing for an empty query) — checking "high priority"
  with nothing typed means "show me what matches that," not "you didn't search for anything."
- **Saved searches are a new, separate server-side entity from ADR 0007's saved date filters** —
  `Store.list_searches`/`save_search`/`update_search`/`rename_search`/`duplicate_search`/
  `set_search_pinned`/`delete_search`, stored under `.trellis.yml`'s `searches` key next to (not
  merged into) `filters`. They hold a different shape (`q`/`tags`/`priority`/`board`/`status`
  criteria, not a date range) and serve a different purpose (pinnable to the sidebar; date filters
  aren't), so keeping them apart avoids one entry type growing optional fields the other never
  uses.
- **A saved search's own URL always carries `?edit=<id>`** (`_search_run_url`): opening one from
  its chip (on Search) or its sidebar pin doesn't just re-run it, it also arms the Advanced Search
  panel's save form to show "Update ‘name’" instead of "Save…" the moment anything changes — one
  mechanism serves both "run it" and "edit it," since editing a saved search *is* running it, then
  changing something.
- **Full management (rename, duplicate, pin, delete) lives in Settings, not a sidebar popover** —
  learned directly from the "Boards in the sidebar" redesign a few commits ago (ADR 0009's second
  amendment): a small popover is the wrong shape for a management UI, even before it has enough
  rows to prove it. The Search page itself only shows a compact chip list (name + a delete-×, same
  shape as ADR 0007's saved-filter chips) — reviewing everything, pinning, renaming and duplicating
  all happen in Settings' new "Saved searches" section, which is unambiguously **not** device-only
  (unlike every other Settings > Sidebar control) since it's shared, server-side state — its
  heading says so rather than reusing the "this device only" tag by habit.
- **Renaming reuses the exact blur-to-save `<input>` idiom already used for board and area titles**
  (`onblur="if (this.value !== this.defaultValue) this.form.requestSubmit()"`) rather than a
  separate rename dialog — one more place doing it the way the rest of the app already does.

## Consequences

- `nav()` (the global template context processor) now also computes pinned searches' URLs on every
  request, one more small per-request cost alongside the sidebar tree and tag counts it already
  builds — consistent with those, not a new pattern.
- `tests/test_search.py` covers `search.refine` directly (tags/priority/board/status, individually
  and AND'd together); `tests/test_store.py` covers the saved-search CRUD methods (including the
  not-found and blank-name error paths); `tests/test_routes.py` and a new e2e test cover the whole
  save → pin → rename → duplicate → delete lifecycle through real requests and a real browser.
- Found while writing that e2e test: Playwright's `has_text` locator filter doesn't see text inside
  an `<input value="...">` (it isn't part of the element's text content). See `AGENTS.md` trap 19.
