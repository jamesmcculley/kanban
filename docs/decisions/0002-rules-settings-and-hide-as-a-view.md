# 0002. Per-board and global rules, layered settings, and hiding as a view

- Status: accepted
- Date: 2026-09-21
- Departs from standard: none

## Context

Wanted Trello-style automation and configuration: for example, checking a task on a board should move it to that
board's Done list. Trello's Butler is large; Trellis needs the useful core without a scripting language.

## Decision

- **Rules** are plain dicts (`when`, `in`, `tag`, `do`, `arg`, `enabled`) stored in YAML, globally
  (`.trellis.yml`) and per board (`board.md`). Triggers: completed, un-checked, added, moved into a list.
  Actions: move, complete, un-complete, add or remove a tag, clear from the list. Global rules run first
  unless the board opts out; then the board's own.
- **Rules never trigger rules.** An action calls the storage layer directly, so a rule cannot loop, and
  behaviour is predictable from the rule list alone. Repeating cards skip rules (they roll forward, they do not finish).
- **The engine is a pure matcher plus a small applier.** `rules.py` and `settings.py` have no I/O; `PreferencesMixin`
  applies the result. A pure-module boundary test enforces it (01).
- **Settings** layer as built-in default, then global, then the board's override; a blank board value means
  inherit. Invalid hand-edited values are ignored, not fatal.
- **Hiding completed cards is a view** (`view_columns`), computed on read from the settings. It never writes,
  which keeps 07's "opening data never writes to it". The Logbook and search still show everything.
- Undo of a completion restores what rules changed (list, position, tags) as well as the done state (08).

## Consequences

- Simple to reason about and to test; no chained automations. A user who wants "move, then complete on arrival"
  writes two independent rules whose conditions do not depend on each other.
- Time-based triggers (due today, overdue) are not supported: they need a scheduler, which needs its own decision.
- List names in global rules that a board lacks are silently skipped for that board.
