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
  `tags.py`, `labels.py`. `tests/test_rules.py::test_domain_modules_are_pure` enforces it. `Store`
  (and its mixins) does the file I/O; `routes.py` is thin HTTP glue.
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
    the moment `KANBAN_PASSWORD` is set. `auth.py`'s login throttle is a plain module-level list,
    correct only because the Dockerfile already commits to one gunicorn worker — the same
    invariant `Store`'s file I/O already depends on (see trap 6's neighbourhood).

## Log

Read `PROJECT_LOG.md` before changing anything. Append to it when behaviour changes.
