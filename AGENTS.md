# Trellis (kanban) — start here

A personal, local-first kanban and task manager: list boards, a flat Tasks-board kind for small
Things3-style to-dos, tags, labels, priorities, start/due dates and repeats, a per-board filter, a
Scheduled view and a Logbook (both with a date-range filter and saved filters), per-board and
global rules, and twelve colour themes. Flask + htmx, no build step. Cards are Markdown files, so
the data folder also opens as an Obsidian vault. Runs on the homelab behind Caddy, LAN-only, behind
a single shared password (`KANBAN_PASSWORD`; see ADR 0005) — localhost deployments never need one.
Status: in daily use. There is no canvas/freeform board and no Inbox board — both were tried and
removed; quick capture (`c`) now asks which board, remembered per device.

## Standards

Follows `~/developer/engineering-standards`. Deviations are ADRs in `docs/decisions/` (0001: Flask, not FastAPI).
Open gaps are tracked in that repo's `ADOPTION.md`. Commit messages: `type(scope): summary`.

## Boundaries

- **Pure domain modules never touch I/O or Flask:** `rules.py`, `settings.py`, `dates.py`, `notes.py`,
  `tags.py`, `labels.py`, `csvimport.py`, `metrics.py`, `search.py`. `tests/test_rules.py::test_domain_modules_are_pure`
  enforces it. `Store` (and its mixins) does the file I/O; `routes.py` is thin HTTP glue.
- **Reading never writes.** Hiding completed cards is a view (`view_columns`), not an archive pass.
- **Files are the source of truth** (Markdown + YAML frontmatter). Unknown frontmatter must survive a save.
- Do not add a database, a JS build step, or third-party runtime requests (htmx and Sortable are vendored).

## Commands

- Verify: `uv run ruff check . && uv run pytest` (unit) then `uv run --with playwright pytest tests/e2e`
  (real Chrome, needs Chrome installed). Run both before saying something works.
- Dev: `KANBAN_DATA_DIR=/tmp/demo uv run flask --app kanban run --debug`
- Deploy (on the ASUS, from the repo): `./deploy.sh`. Backup: `scripts/backup.sh`. Restore drill: `scripts/restore-check.sh BACKUP.tar.gz`.

## Traps

1. **htmx drops clicks on freshly swapped nodes for 20 ms** (settle delay; `keys.js` sets it to 0) and while an
   `htmx.ajax` call with no source element is pending. Use plain `fetch` for background calls.
2. **Sortable will not start a drag from an `<a>`.** Card titles are `<span role=button>` for that reason.
3. **Colours come from tokens** (`themes.css`, `app.css`). Never hard-code a colour; never use raw
   `--text-muted` or `--accent` for text (they fail WCAG AA; use `--text-subtle`, `--accent-text`).
   `tests/test_themes.py` checks every theme.
4. **Rules must not chain** (an action never fires another rule) and must skip repeating cards.
5. HTML is served `Cache-Control: no-store` on purpose (Back must not show a stale board). Writes require
   a same-origin `Origin` header (`refuse_cross_origin_writes`); tests using the Flask client send none, which is allowed.
6. **A client that fires several requests at once against the same file (e.g. hiding every list) must
   await them one at a time, not `Promise.all`.** Each one is a read-modify-write of `board.md`; run
   concurrently, the last writer clobbers the others silently. Found via the real-browser "Hide all"
   test, not by reasoning about it in advance — a reminder that e2e tests catch races unit tests can't.
7. **`window.moveCard` and the sidebar drop handler hardcode `document.querySelector('.board')`** for
   their move URLs. Any new board-like page (e.g. `tasks.html`) must put the `.board` class (plus
   `data-move-url`/`data-moveboard-url`) on its own container — a differently-named wrapper silently
   breaks drag/move with no error.
8. **Jinja's default `Undefined` raises on `{% for %}` but not `{% if %}`.** `board_settings.html`
   passes `{}` (no `rules`/`recipes`/`triggers`/...) for a non-kanban board, so the whole "Rules for
   this board" section is gated behind `{% if board.kind == 'kanban' %}` rather than relying on
   `_rules.html`'s internal `{% if rules %}` — that guard alone isn't enough, since `_rules.html` also
   has an unconditional `{% for recipe in recipes %}` that would 500 on an undefined `recipes`.
9. **`filter.js` grabs the page's first (and only expected) `.filter-wrap` unconditionally** — any
   other popover that reuses that class name (even just to inherit its floating-panel CSS) gets
   silently mistaken for the per-board filter and crashes the moment its panel receives an `input`/
   `change` event. The Scheduled/Logbook date-range popover shares the *look* (`.filter-panel` for
   CSS) but uses its own `.date-filter-wrap`/`.date-filter-panel` classes and a separate toggle
   (`data-date-filter-toggle`, handled in `ui.js`) for exactly this reason.
10. **`/api/health` is registered directly on `app`, not on the `boards` blueprint** (`__init__.py`,
    not `routes.py`) — its endpoint name is `"health"`, not `"boards.health"`. `require_login`'s
    exempt-endpoints check has to use the bare name, or the container healthcheck starts failing
    the moment `KANBAN_PASSWORD` is set. `auth.py`'s login throttle is a plain module-level list;
    that only works at all because of one gunicorn *worker* (`--workers 1`, same invariant
    `Store`'s file I/O depends on — see trap 6's neighbourhood), not because it's single-threaded
    (`--threads 4`). It's still not locked: a little imprecision under real concurrent requests is
    an accepted trade-off for a personal app's login throttle, not a bypass — see `auth.py`'s
    comment on `_recent_failures` before tightening it.
11. **A redirect target built from user input needs more than `not candidate.startswith("//")`.**
    Browsers normalize `\` to `/` when resolving a URL, and strip ASCII tab/newline/CR *before*
    that — so `next=/\evil.example` and `next=/<TAB>/evil.example` both collapse to
    `//evil.example` and leave the app's own origin, even though neither string starts with `//`
    when the server sees it. `auth._safe_next` checks for all of `\`, tab, newline and CR, not
    just a leading `//`. Verified against a real browser's `URL` parser, not just reasoned about —
    the failure mode is invisible in curl/Python, which don't do this normalization.
12. **A script that scans `.card` elements once when it loads misses every card added afterward.**
    `filter.js`'s per-board filter builds its tag checkbox list once from whatever's in the DOM at
    load time; cards added later arrive via htmx, after that scan already ran, so their tags never
    showed up as filter options without a full page reload. Fixed by rebuilding that list each time
    the filter panel opens (cheap, and matches when a stale list would actually be noticed), not
    just once — found by an e2e test that added a card and then opened the filter in the same test,
    which a test that reloads the page in between never would have caught.
13. **A flex item shrinks by default, `overflow: auto` or not.** `.sidebar nav` is a `flex-direction:
    column` container relying on its own `overflow-y: auto` to scroll past too much content — but
    its *children* (the board list, areas, tags) are flex items too, and flex items default to
    `flex-shrink: 1`. With enough boards/areas/tags to actually overflow, the browser shrank those
    children to fit instead of letting nav scroll past them, so the next section rendered
    overlapping the tail of the one before it — not a missing scrollbar, an invisible one. Fixed
    with `.sidebar nav > * { flex-shrink: 0; }`. Existed since the original collapsible-sidebar
    work; never showed up in testing because nothing before had `test_sidebar_footer_never_needs_
    scrolling`'s 15 areas *and* enough total height to overflow a short viewport at the same time —
    `to_be_in_viewport()` on the footer doesn't catch content overlapping *itself* elsewhere in the
    sidebar. `test_sidebar_sections_dont_overlap_when_nav_needs_to_scroll` checks bounding boxes
    directly for exactly that.
14. **An empty container has no bounding box, so Playwright's `to_be_visible()`/`is_visible()` calls
    it invisible even when nothing is actually hiding it.** `#tag-section` renders nothing when a
    board has no tags at all — a test toggling "Show in the sidebar > Tags" on a fresh board with no
    tagged cards saw `visible: False` both before *and* after re-enabling it, which looked like the
    show/hide toggle was one-way. It wasn't; the div was just genuinely empty. Any test asserting
    visibility of a section that can legitimately have no content needs real content in it first —
    `test_hide_a_sidebar_section_live_and_persisted` adds a tagged card before touching the toggle.
15. **The sidebar footer icons (`.side-foot`) are `position: fixed`, not part of the sidebar's
    flex/scroll flow** — same idea as the FAB, mirrored bottom-left, so they're reachable no matter
    how nav's flex math resolves. Left nested inside `.sidebar` in the markup on purpose (hides for
    free when the sidebar collapses), but because a `position: fixed` element reserves no space in
    normal flow, `.sidebar nav` needs its own `padding-bottom` or scrolled content renders
    underneath the floating pill instead of stopping above it.
16. **A flex item at `opacity: 0` still occupies its layout space** — it's invisible, not gone.
    Skinny mode's board rows (72px wide, ~40px after padding) hid `.pin-btn` with hover-only
    `opacity`, same as everywhere else it appears, but at that width its ~16px was most of the row:
    the title span was left with ~1px and rendered nothing, not even a truncated letter. One row
    (the active one, with a background colour) still looked like *something* was there; a second,
    inactive row looked like the board had vanished from the sidebar entirely. Fixed with
    `display: none` on `.pin-btn` specifically in skinny mode, freeing the space for real.
    (Skinny mode itself was later removed — see ADR 0007's amendment — but the underlying lesson,
    that a hover-reveal via `opacity` isn't free at a narrow enough width, still generalizes.)
17. **A board page and the sidebar can each show a "reveal a checklist panel" popover at once, and
    reusing the same generic classes for both (`.eye-menu-wrap`, `[data-eye-toggle]`, `.eye-menu`,
    `.eye-row`, `.icon-badge`) is exactly right for the shared open/close JS -- ui.js's handler
    doesn't care which panel it's toggling -- but wrong for anything that queries by class alone.**
    Adding the sidebar's "show/hide boards" panel (same look as the per-board "show/hide lists"
    one) made `.eye-menu`, `.eye-row` and `[data-eye-toggle] .icon-badge` match two elements on any
    kanban board page, and existing Playwright locators using those classes unscoped hit strict-mode
    violations. Same shape as trap 9's `.filter-wrap` collision. Fixed by scoping each test's
    locator to its own panel's container (`.page-head .eye-menu` vs `.side-boards-head .eye-menu`)
    and giving the sidebar's badge its own class (`.board-hidden-badge`, same CSS rule as
    `.icon-badge`, just not the same selector) rather than trying to make one class disambiguate.
18. **A Playwright `get_by_role(name=...)` match is by accessible name, not by page section** --
    adding the sidebar's "Today" nav link gave the page a second thing named "Today" (the
    Scheduled/Logbook date filter already had a "Today" preset chip), and an existing test's
    `get_by_role("link", name="Today", exact=True)` started matching both. `exact=True` only
    stops substring matches; it does nothing about two unrelated elements sharing the exact same
    name. Fixed by scoping the locator to its actual container (`.date-filter-panel`). Same root
    cause as trap 17, one level up (accessible name vs. CSS class).
19. **Playwright's `has_text` matches rendered text content, not an `<input value="...">`.** The
    saved-search rows in Settings show each search's name in an editable `<input>` (same blur-to-
    save idiom as board/area titles), and `page.locator(".saved-search-row", has_text="Home
    stuff")` never matched it — an input's value isn't part of its element's text content the way
    a `<span>`'s text is. Fixed by filtering on the input itself (`:has(input[value="..."])`)
    instead. Worth remembering anywhere a row's identifying text lives in an editable field rather
    than plain text, which by now is most rename-in-place UI in this app.
20. **Two elements deliberately centered on the same edge will fight over the same pixels unless
    something explicitly yields.** The sidebar's collapse button sits centered vertically right on
    top of the resize handle's edge (on purpose — that's the whole design). Left alone, the
    higher-z-index button silently swallowed every resize drag that started anywhere near vertical
    center, since `bounding_box()`-style hit-testing has no idea one element sits above another.
    Fixed with `clip-path` on the resize handle, cutting a hole in its hit area the size of the
    button's own footprint — `clip-path` affects pointer events, not just paint, so the cut-out
    band passes clicks through to the button underneath instead of eating them. The e2e drag tests
    had to move their target Y off the exact vertical center for the same reason.
21. **A `title` attribute is not an element's accessible name when it also has visible text
    content — the text wins.** The card-edit dialog's new Duplicate button (icon + the word
    "Duplicate", plus `title="Duplicate this card"` for the tooltip) has an accessible name of
    just "Duplicate", not "Duplicate this card": `title` only becomes the accessible name when
    there's *no* text content to use instead. `page.get_by_role("button", name="Duplicate this
    card")` timed out finding nothing; `name="Duplicate"` (the visible text) found it immediately.
22. **Dropping a card outside every Sortable-managed list still fires that Sortable's `onEnd`** --
    it only tracks the dragged item's index *within its own list*, has no idea the actual drop
    landed somewhere else, and fires a same-list reorder POST for whatever index drift happened
    along the way (the cursor passing near a sibling card en route is enough to cause drift, even
    with no real reorder intended). This is the `test_drag_card_onto_sidebar_board_moves_it_with_
    undo` flake from ADR 0007 finally root-caused: dragging a card onto a sidebar board fires two
    real, concurrent writes to the same card -- Sortable's own spurious `/cards/<id>/move`
    (same-board reorder) racing the sidebar drop handler's real `/cards/<id>/move-board`
    (cross-board move) -- and depending on timing, the reorder's write can land *after* the move
    already relocated the card's file to the other board's folder, resurrecting a stale duplicate.
    Confirmed by measurement, not just reasoning: reverted the fix and ran the test 10x (3
    failures) vs. 23x with the fix applied (0 failures). Fixed at the source, not by locking files
    -- `window.__sidebarDropHandled`, set synchronously in the sidebar drop handler (ui.js) before
    its async fetch even starts, and so guaranteed to be set before the native `dragend` that
    drives `onEnd` (dragend always fires after drop) -- tells the board's own Sortable `onEnd`
    (board.html, tasks.html) this drop is already spoken for, skip your own reorder.
23. **A two-step "click again" confirm button (`arm()`, ui.js) appends its confirm text as a child
    span, changing the button's own text content on the very first click.** A button named only by
    its text content (no `aria-label`) therefore has a *different* accessible name after arming
    than before — a locator (or screen reader) that found it by name pre-arm won't find it again
    for the second, confirming click. The bulk-delete button (ADR 0015) hit this in its own e2e
    test; the existing "Delete board" button already avoided it by having an explicit
    `aria-label="Delete board"` (which wins over text content regardless of what the text becomes)
    — every `data-confirm` button needs one for the same reason, not just for screen readers.
24. **`write_md()` used to write straight to the target path** (`Path.write_text`), not atomically
    — a concurrent read landing between the truncate and the new content finishing could see a
    half-written file and crash (`KeyError` on a required field like `id`). Hit for real by an e2e
    run: `/sidebar/stats` (fetched after nearly every card action) raced an in-flight card save.
    Now writes to a `.tmp` sibling and `Path.replace()`s it into place, which is atomic on POSIX and
    Windows — a reader always sees either the whole old file or the whole new one. Confirmed the
    fix actually matters (not just theoretical) by reverting it and watching
    `test_reading_cards_while_writing_never_sees_a_half_written_file` fail with the exact same
    `KeyError('id')` from the real crash, then reapplying it and watching that test pass.

## Log

`PROJECT_LOG.md` is a local, gitignored working journal — it won't be in a fresh clone. If it
exists in your checkout, read it before changing anything and append to it when behaviour changes.
