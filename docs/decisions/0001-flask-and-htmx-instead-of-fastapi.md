# 0001. Flask with server-rendered HTML and htmx, not FastAPI or a TypeScript SPA

- Status: accepted
- Date: 2026-09-21
- Departs from standard: 03 (Python services use FastAPI) and 02 (default stack is TypeScript + React)

## Context

Trellis is a single-user app whose data is Markdown files. The owner works mostly in Python and wanted the
whole app in it. The interface is a set of server-rendered pages with small islands of behaviour (drag and
drop, inline edit, toasts), not a client-side application with its own state.

## Decision

Flask, Jinja templates and htmx, with vanilla JavaScript for the islands. No build step, no bundler. htmx and
SortableJS are vendored under `static/vendor/` (02: no runtime CDNs). The one canonical state model is the
files on disk; every page is a projection of it.

## Consequences

- No Python type-checking gate or FastAPI schemas yet. Input is validated in pure modules (`settings.py`,
  `rules.py`) and at the route boundary, but there is no `mypy` step (a gap in ADOPTION).
- Server-rendered pages mean state that affects trust (saved, error) is shown in the response, not in a client store.
- If the app grows a real client-side state need (offline editing, live multi-device sync), revisit with a new ADR.
