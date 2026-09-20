# Kanban

A local-first kanban board. Cards are plain Markdown files with YAML frontmatter, so the data
directory can also be opened as an Obsidian vault.

- Boards of lists, drag-and-drop cards, Markdown notes, tags (`#home`), completion timestamps
- Natural-language dates and repeats: `Pay rent tomorrow`, `fri`, `in 3 days`, `Water plants every monday`
- Today and Upcoming views across all boards; search; keyboard shortcuts (press `?`)
- Sidebar with areas (groups of boards); drag to reorder boards, areas and lists; hide lists you don't need right now
- Canvas boards: a freeform surface for notes, links, images (paste or drop) and nested boards

## Run locally

    uv sync
    uv run flask --app kanban run --debug

Data lives in `~/kanban-data` (override with `KANBAN_DATA_DIR`). Each board is a folder: `cards/` or
`items/` (Markdown files), plus `assets/` for canvas images. Area order is kept in `.trellis.yml`.

## Docker

    cp .env.example .env    # set PROXY_NETWORK to your reverse proxy's network
    docker compose up -d --build

The container listens on port 8000 on that network only (no published ports). There is
**no authentication**, so put it behind a proxy route restricted to your LAN or VPN.

## Backups

`scripts/backup.sh` writes a timestamped tarball of the data volume and prunes old ones. Run it
from cron or a systemd timer on the Docker host; the header comment lists the settings and the
restore command. Keep a copy off the machine too.

## Develop

    uv run pytest
    uv run ruff check .
    uv run --with playwright pytest tests/e2e   # real-browser tests; needs Chrome installed
