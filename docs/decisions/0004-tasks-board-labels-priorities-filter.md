# 0004. Tasks board kind, labels, priorities, and a per-board filter

- Status: accepted
- Date: 2026-09-22
- Departs from standard: none

## Context

Three features were requested together, after 0003 shipped: a lightweight Things3-style task list
("little tasks that aren't really worthy of a board... best of both worlds"), labels and priorities
on cards, and a per-board search/filter over any criteria (text, labels, priorities, tags).

## Decision

- **Tasks board kind.** `BOARD_KINDS = ("kanban", "tasks")`. A tasks board is, underneath, an
  ordinary kanban board with exactly one column (`TASKS_COLUMN = "Tasks"`) — it reuses the existing
  Card/column machinery entirely (add, complete, delete, reorder, drag, rules-adjacent plumbing)
  rather than a parallel data model. `tasks.html` renders it as a flat list: no list-title/hide/delete
  controls, just an add-task input and cards. `nav()`'s board list, `all_cards()`, and
  `move_card_to_board()` all treat `kind in ("kanban", "tasks")` as a card-holding board; only rules
  (which reason about lists) stay kanban-only, gated at the route level in `board_settings()`.
- **Labels.** Board-scoped, not global: `{id, name, color}` stored in `board.md`, referenced from a
  card by id (`labels.py`, pure — validation only, no I/O). Color is one of a fixed 10-name palette
  (`labels.COLORS`), each checked to read at ≥4.5:1 with either black or white text — never an
  arbitrary hex, so contrast and consistency don't depend on what the owner picks. Distinct from tags
  (free-text, shared across every board, no color): a label is a small structured set you manage per
  board, closer to Trello's label model.
- **Priorities.** `PRIORITIES = ("low", "medium", "high")`, a plain optional field on `Card`, no
  board-level configuration. Deliberately not a fourth "urgent" tier or a numeric scale — three
  options cover the actual use case and need no settings UI of their own.
- **Per-board filter.** Text, labels, priority and tags, narrowing the current board in place.
  Deliberately client-side only (`filter.js`, `.card` elements carry `data-labels`/`data-priority`/
  `data-tags`) rather than a server round-trip or persisted state: it's a live view over cards already
  on the page, not a saved search — that need is already met by Scheduled's saved filters (0002-era
  work), which operate over dates across every board instead of one board's own criteria.

## Consequences

- `Card` and `Board` both grew fields (`labels`, `priority` on `Card`; `labels` on `Board`); every
  `update_card`/`add_card` caller had to be re-checked for silent field loss — `toggle_task()` was
  the one real near-miss, caught before it shipped by grepping every `update_card(` call site rather
  than by a failing test.
- `board_settings.html`'s rules section had to be gated on `board.kind == 'kanban'` rather than
  trusting `_rules.html`'s own `{% if rules %}`, since Jinja's default `Undefined` raises on the
  template's unconditional `{% for recipe in recipes %}` (AGENTS.md trap 8).
- `tasks.html` reuses the `.board` CSS class (not a new one) on its container specifically so
  `window.moveCard` and the sidebar drop handler — both hardcoded to `document.querySelector('.board')`
  — keep working without their own tasks-board-aware branch (AGENTS.md trap 7).
- The filter is per-page and resets on reload by design; it does not (yet) filter Scheduled or the
  Logbook. Priority and label chips were added to Scheduled and Search's row views too (so a
  priority set on a card is visible everywhere it appears), but not to the Logbook's rows — a small,
  accepted inconsistency rather than touching one more template for a secondary view.
