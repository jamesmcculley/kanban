# 0005. A single shared password, LAN mode only

- Status: accepted
- Date: 2026-09-22
- Departs from standard: none

## Context

The app has never had a login: LAN mode relied entirely on Caddy's `remote_ip` allow-list to keep
it off the wider internet, and localhost mode relied on binding to `127.0.0.1`. The owner asked
whether a login page made sense, for LAN mode and for localhost mode separately.

The two modes have different threat models. Localhost mode is reachable only by processes on that
one machine; if something unauthorized can already reach `127.0.0.1:8000`, it's because it has
local OS access, at which point an app-level password adds little (the attacker already has the
filesystem, the browser session, everything else on the box). LAN mode is reachable by every device
on the network — a guest's phone, a compromised IoT device, anything on that Wi-Fi — which an IP
allow-list can't distinguish between. That gap is what a login closes.

## Decision

- **`KANBAN_PASSWORD`** (env var, or `create_app(password=...)` for tests): unset means the app
  behaves exactly as before this existed — every route open, no session, no login page. Set means
  every route requires an authenticated session except `/login`, `/logout`, static assets (the
  login page has to load its own CSS) and `/api/health` (the container healthcheck must keep
  passing regardless of login state).
- One shared password, not accounts. This is a personal app for one household, not a multi-tenant
  system — a login system with usernames, password resets and per-user permissions would be
  machinery this app has no use for.
- `docker-compose.yml` (the LAN-hosted setup) now requires `KANBAN_PASSWORD` in `.env`
  (`${KANBAN_PASSWORD:?set KANBAN_PASSWORD in .env}`, same pattern as `PROXY_NETWORK`) — LAN mode
  fails to start rather than silently deploying unauthenticated. `docker-compose.localhost.yml`
  never sets it, on purpose; localhost mode stays login-free.
- The session-signing key is derived from the password itself (`sha256("trellis-session-key:" +
  password)`) rather than a separately generated and stored secret. Trade-off, taken deliberately:
  no extra secret file to generate, persist across redeploys, or lose; changing the password
  invalidates every existing session for free; but the signing key is only as strong as the
  password, so a weak password (a 4-digit PIN) weakens session forgery resistance too, not just
  login brute-forcing. README asks for a real passphrase, not a PIN.
- A simple in-memory throttle (5 failed attempts / 5 minutes, then 429) guards the login form
  itself. It lives in a plain module-level list, which only works at all because of one gunicorn
  *worker* (`--workers 1`, the same invariant `Store`'s file I/O already depends on) — not because
  requests are single-threaded (`--threads 4` still runs concurrently in that one process). It
  isn't locked; a little imprecision in the count under real concurrent requests is accepted as a
  trade-off, not treated as a bypass, for a throttle this low-stakes.
- `auth._safe_next` (the post-login redirect target) rejects more than a leading `//`. Verified
  against a real browser's URL parser (not just reasoned about, since curl and Python don't
  reproduce this): backslash is normalized to `/` for special schemes, and ASCII tab/newline/CR
  are stripped *before* that — so `next=/\evil.example` and `next=/<TAB>/evil.example` both
  resolve to `http://evil.example/` in a real browser even though neither starts with `//` when
  the server sees it. `_safe_next` now also rejects `\`, tab, newline and CR.
- `refuse_cross_origin_writes` (existing, pre-dates this ADR) becomes more important, not less: a
  session cookie is sent automatically to any request that reaches the app's origin, so a page on
  another site riding a logged-in browser's cookie is now a real CSRF-shaped risk where before
  there was no session to ride. `SESSION_COOKIE_SAMESITE=Lax` adds a second, browser-enforced layer
  on top of the existing Origin/Sec-Fetch-Site check.
- Not done: `SESSION_COOKIE_SECURE`. Forcing it would break login over plain HTTP (local testing of
  `docker-compose.yml` without Caddy in front, or the e2e test server). The real LAN deployment is
  already served over HTTPS via Caddy per the standing runbook, so the password isn't sent in the
  clear in practice; this is a documented expectation (README), not an enforced one.

## Consequences

- Existing LAN deployments (the ASUS) must set `KANBAN_PASSWORD` before their next `./deploy.sh` or
  the compose file refuses to start — a deliberate fail-fast rather than a silent gap.
- A board opened from an old bookmark or a saved capture-board preference still needs a fresh login
  after the session expires (30 days) or the password changes; nothing else about the app's data or
  URLs changes.
- `base.html`'s sidebar footer gains a "Log out" icon, shown only when `auth_enabled` (i.e. only in
  LAN mode with a password set) — invisible and irrelevant in localhost mode.
