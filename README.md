# Kanban

A local-first kanban board. Cards are plain Markdown files with YAML frontmatter, so the data
directory can also be opened as an Obsidian vault.

- Boards of lists, drag-and-drop cards, tags (`#home`), Markdown notes with live checklists
- **Import from CSV** — one row per card (title, list, dates, tags, priority, notes) — into a new
  board or an existing one; a kanban board creates any list it doesn't already have
- **Tasks boards**: a flat, Things3-style list for small to-dos that don't need a whole board of lists
- **Labels** (a small named, coloured set per board) and **priorities** (low/medium/high) on any card
- A **per-board filter** — text, labels, priority, tags — that narrows the board in place, client-side
- **Advanced Search** — narrow by title/notes text, tags, priority, board and open/done status,
  combined; **save a search and pin it to the sidebar**, rename, duplicate or delete it from Settings
- Natural-language start and due dates, and repeats: `Pay rent tomorrow`, `fri`, `in 3 days`, `Water plants every monday`
- **Move or duplicate any card** from its edit dialog — reachable from a board, Scheduled, the
  Logbook, Today or Search, so it works the same "from anywhere," not just by dragging on a board;
  duplicate lands on whatever board/list the "Move to" picker has selected, or right where it was
- **Duplicate a whole board** — a full copy, cards (including done ones), lists, settings, rules
  and labels all included
- **Bulk actions**: select several cards on a board (the checkbox icon) and move, duplicate or
  delete all of them at once
- **Rules and settings**, per board and global: e.g. "when a card is completed, move it to Done"; new-card
  position; hide completed cards; default lists for new boards; hide list/board titles or card counts
- Twelve colour themes plus a Default that follows your device, and three text sizes (Settings)
- Quick capture (`c` from anywhere) to a board of your choice, remembered per device
- **Today**: what's due or overdue, what you completed today and what you created today, in one
  place — each of the three sections can be hidden from the page itself
- **Scheduled**: every card with a start or due date, across all boards, with a date-range filter,
  quick presets and filters you can save and reuse
- A Logbook of everything you've completed (with the board and list it came from), the same date
  filter, and an edit (pencil) button on each entry to fix anything about it — not just when it
  was completed
- **Metrics** (toolbar icon): totals for a date range, plus busiest board and busiest day of the
  week, as simple bar charts — narrow it by text, tags, priority or board, same as the export below
- **Review mode**: a quick "what did I do / what am I doing" report — completed in the last N
  days, due or upcoming in the next N days (both free text, adjustable on the page, 0 means "show
  nothing that direction"); **star** a card (from its edit dialog or a Review row) to always
  highlight it; check **"only starred items"** to ignore the date range entirely and see every
  starred card ever — built for an annual review
- **Hide any card** from every card-listing view at once (a board, Today, Scheduled, Logbook,
  Review, Search, Metrics) without archiving or deleting it — a quick button on the card itself,
  wherever it's shown; revived from a "Hidden cards" eye icon on its own board or task list, same
  as reviving a hidden list — or from a cross-board "Hidden cards" list in Settings, if you don't
  remember which board it was on
- **Collapsible sections** on Today, Scheduled, Logbook and Review — fold any section or per-day
  group out of the way with the chevron on its heading; remembered per device
- **Reorder Today's "Due & overdue" list by dragging** — a real manual priority order that
  overrides date sorting entirely, so an old overdue task can sit below something due today
- **Export to CSV** — completed activity from Metrics or the Logbook; real cards from any board,
  Scheduled, Today or Review — each a pop-out for granular options (text, tags, priority,
  board/list, Today/Review's own sections), not just everything in one shot. A board's export is
  the same shape CSV import reads, so export → edit → re-import is a real round trip
- An edit button right on a Scheduled card, so you don't have to go find it on its board
- Undo for deletes and completions; deleted things wait in a Trash until you empty it
- **Archive a board** to tuck it out of the sidebar, search and Scheduled without deleting it — its
  cards, rules and history stay exactly as they were; unarchive it any time from its own page or the
  Archived boards list
- Sidebar with areas, boards you can rename or delete, drag-to-reorder for boards, areas and lists;
  open or hidden (a single arrow button centered on its edge), plus a resizable width (drag the
  edge, or type a number in Settings)
- **Sort boards** alphabetically, most recently updated or most recently created, or drag them
  manually (Settings) — and **show or hide any sidebar section** (logo, search, Today, Scheduled,
  Logbook, Review, boards, tags, the theme toggle) except the toolbar at the bottom, so there's
  always a way back in; **show or hide the page heading** on Today, Scheduled, the Logbook and
  Review, too
- **Pin a board** to keep it at the top of its list no matter which sort order is active
- **Hide a board from the sidebar** — hover a row for a one-click hide button, or manage the whole
  list at once from Settings ("Boards in the sidebar," grouped by area) — separately from a "show
  or hide lists" panel (the eye icon on a board itself) to see and toggle every list's visibility
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

## License

MIT — see [LICENSE](LICENSE).
