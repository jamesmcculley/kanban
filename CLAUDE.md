@AGENTS.md

## Claude Code specifics

- For UI work, drive real Chrome with Playwright (`tests/e2e`, see AGENTS.md). Unit tests alone missed several
  real bugs here (draggable titles, stale clicks, focus races), and screenshots caught layout problems.
- Prefer `uv run python` and `uv run --with playwright ...` over installing anything globally.
