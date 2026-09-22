# Project log

## Systems map

- **App:** Flask (`src/kanban`). `routes.py` is HTTP glue; `Store` (`store.py`) plus mixins (`trash.py`,
  `logbook.py`, `preferences.py`) own all file I/O; pure modules hold the logic (`rules.py`, `settings.py`,
  `dates.py`, `notes.py`, `tags.py`, `labels.py`). No canvas/freeform-board code — tried (2026-09-19), removed
  (2026-09-22). Two board kinds: `kanban` and `tasks` (a flat, single-column Things3-style list).
- **Data** (`KANBAN_DATA_DIR`, a named volume in Docker): one folder per board with `board.md` and `cards/`;
  root files `.trellis.yml` (areas, global settings and rules, saved filters, `format: 1`),
  `.trellis-log.jsonl` (Logbook), `.trash/`. All Markdown/YAML/JSON, readable in Obsidian.
- **Frontend:** server-rendered Jinja, htmx and SortableJS (vendored), vanilla JS in `static/` (`ui.js`, `keys.js`,
  `toast.js`, `fab.js`, `sidebar.js`, `theme.js`). Colours: `themes.css` (shared 12 themes) + `app.css`.
- **Host:** the ASUS, container `kanban` on the shared Caddy network, LAN-only route in the dashboard repo's
  Caddyfile. Deploy with `./deploy.sh` on the host. Nightly cron runs `scripts/backup.sh` at 03:15.

## Gotchas

- htmx: 20 ms settle delay ignores clicks on new nodes; a pending `htmx.ajax` without a source element blocks other
  requests; Sortable cannot drag from an `<a>`. See AGENTS.md traps.
- Jinja: a dict passed to a template that has an `items` key collides with `dict.items`.
- `git pull` replaces the Caddyfile inode; Caddy must be recreated to see it (see the standards runbook).
- Raw `--text-muted` and `--accent` fail WCAG AA in the shared themes; use the derived tokens.
- Client-side bulk actions against the file store must `await` one request at a time, never
  `Promise.all` — concurrent read-modify-writes to the same `board.md` silently clobber each other.
  See AGENTS.md trap 6.

## Changelog

- 2026-09-22 — Decluttered several always-visible controls behind buttons/badges, same pattern as the
  per-board filter: Scheduled/Logbook's preset chips, saved filters, and custom From/To range all now
  live behind a single filter icon (was: a permanently-open date form plus a chip row); a board's
  existing labels show as a plain chip until "Edit" is clicked, instead of every label's name field
  and full 10-swatch colour picker being permanently expanded; the "N lists hidden" text chip next to
  a board's title is gone, replaced by a small count badge on the eye icon itself.
- 2026-09-22 — Tasks board kind (a flat Things3-style list for small to-dos, reusing the kanban card
  machinery with one hidden column); board-scoped labels (`labels.py`, a fixed 10-colour AA-checked
  palette) and card priorities (low/medium/high); a per-board filter (text, labels, priority, tags) —
  entirely client-side, hides non-matching cards in place, no server round-trip. `move_card_to_board`
  now accepts a tasks board as a destination. See ADR 0004.
- 2026-09-22 — Start dates alongside due dates; Today+Upcoming merged into Scheduled with a date-range
  filter, presets and saved filters (shared with a new Logbook filter); editable completion date/time
  (forgot to check something off on time); "Move to" any list on any board from the edit dialog; a
  hidden-lists panel (toggle each or all); collapsible sidebar; per-board/global toggles for list/board
  titles and card counts. Removed the canvas/freeform board (unused; zero boards used it) and the
  pinned Inbox board (quick capture now asks which board, remembered per device).
- 2026-09-21 — Shared colour themes (12 + Default) with a Settings picker and text size; AA-safe derived tokens.
- 2026-09-21 — Global and per-board settings and rules (checking a card can move it to Done); hide-completed as a view;
  settings and rules pages; undo restores what a rule did.
- 2026-09-21 — Origin check on writes, security headers, `/api/health`, `deploy.sh`, `restore-check.sh`; unknown
  frontmatter is preserved on save.
- 2026-09-20 — Undo, Trash, Logbook, Inbox, drag-to-board, Markdown notes with checklists, install support.
- 2026-09-19 — First deploy: list boards, due dates and repeats, canvas boards, areas, tags, reordering.
