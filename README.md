# Kanban

A local-first kanban board. Cards are plain Markdown files with YAML frontmatter, so the data
directory can also be opened as an Obsidian vault.

- Boards of lists, drag-and-drop cards, tags (`#home`), Markdown notes with live checklists
- **Tasks boards**: a flat, Things3-style list for small to-dos that don't need a whole board of lists
- **Labels** (a small named, coloured set per board) and **priorities** (low/medium/high) on any card
- A **per-board filter** — text, labels, priority, tags — that narrows the board in place, client-side
- Natural-language start and due dates, and repeats: `Pay rent tomorrow`, `fri`, `in 3 days`, `Water plants every monday`
- **Move any card to any list on any board** from its edit dialog, not just by dragging
- **Rules and settings**, per board and global: e.g. "when a card is completed, move it to Done"; new-card
  position; hide completed cards; default lists for new boards; hide list/board titles or card counts
- Twelve colour themes plus a Default that follows your device, and three text sizes (Settings)
- Quick capture (`c` from anywhere) to a board of your choice, remembered per device
- **Scheduled**: every card with a start or due date, across all boards, with a date-range filter,
  quick presets and filters you can save and reuse
- A Logbook of everything you've completed (with the board and list it came from), the same date
  filter, and a way to fix a completion date you forgot to check off on time
- Undo for deletes and completions; deleted things wait in a Trash until you empty it
- Sidebar with areas, boards you can rename or delete, drag-to-reorder for boards, areas and lists,
  and a collapse toggle
- A "show or hide lists" panel (the eye icon) to see and toggle every list's visibility at once
- Installable to a phone's home screen; keyboard shortcuts (press `?`)
- A login for LAN mode (one shared password; not needed, and not offered, in localhost mode)

## Installing

Pick a mode based on who should be able to reach the app — this is the one decision that matters
before you install it.

| Mode | Who can reach it | Login | Good for | Not for |
| --- | --- | --- | --- | --- |
| **Localhost** | Only this machine | None — nothing to add when only your own OS account can reach the port | One person, one computer; anything sensitive | Your phone, or anyone else |
| **LAN** | Every device on your network | One shared password (`KANBAN_PASSWORD`) | A household sharing boards, using it from a phone | Sensitive data, unless the network itself is trusted and segmented |

Never expose either mode directly to the internet, even with the LAN password set — it's one shared
password with a simple throttle, not built to survive internet-scale guessing. If you need off-LAN
access, put a VPN into your LAN in front of it instead.

### Localhost, no Docker

    uv sync
    uv run flask --app kanban run

Flask's dev server binds to `127.0.0.1` by default — confirmed with `lsof`, not assumed. Nothing
outside this machine can reach it. Leave off `--debug` for anything you'll keep running: it enables
an interactive in-browser debugger, which is a code-execution risk on a process left up for days.

### Localhost, in Docker

    docker compose -f docker-compose.localhost.yml up -d --build
    open http://localhost:8000

This is `docker-compose.yml`'s isolation (non-root, read-only, no secrets) with the port published
to `127.0.0.1` only, and no reverse proxy or `.env` required. Verified end to end (built, started,
answered on `127.0.0.1`, healthcheck passed) with no other services running.

### LAN, behind a reverse proxy

    cp .env.example .env    # set PROXY_NETWORK and KANBAN_PASSWORD
    docker compose up -d --build     # or, on the host, ./deploy.sh (backs up, pulls, rebuilds)

The container publishes no ports of its own; it only joins your proxy's Docker network. Your proxy
should still restrict the route to your LAN or VPN (a `remote_ip` allow-list in Caddy, for example)
as a second layer, on top of — not instead of — `KANBAN_PASSWORD`, which this mode requires (the
compose file refuses to start without it). Pick a real passphrase, not a PIN: it doubles as the
key that signs login sessions, so a weak password weakens more than just the login form. Serve LAN
mode over HTTPS (Caddy does this already if you're following the runbook below) — the password
travels in the clear otherwise. `engineering-standards/standards/11-asus-host-runbook.md` has the
full add-an-app checklist if you're deploying next to other apps this way.

## Data

Data lives in `~/kanban-data` (override with `KANBAN_DATA_DIR`; the Docker modes use a named volume
instead). Each board is a folder of `cards/` (Markdown files). Area order and saved filters are kept
in `.trellis.yml`, the Logbook in `.trellis-log.jsonl`, and deleted things in `.trash` folders (all
hidden from Obsidian). Board settings and rules live in each `board.md`; global ones in
`.trellis.yml`. Frontmatter fields this app doesn't know are kept when it saves.

## Themes

`static/themes.css` is the shared palette from `engineering-standards/standards/13-themes.md`. Pick a theme in
Settings; it is remembered per device and applied before the page paints.

## Backups

`scripts/backup.sh` writes a timestamped tarball of the data volume and prunes old ones. Run it
from cron or a systemd timer on the Docker host; the header comment lists the settings and the
restore command. Keep a copy off the machine too.

## Develop

    uv run pytest
    uv run ruff check .
    uv run --with playwright pytest tests/e2e   # real-browser tests; needs Chrome installed
