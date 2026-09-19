# Kanban

A local-first kanban board. Cards are plain Markdown files with YAML frontmatter, so the data
directory can also be opened as an Obsidian vault.

- Boards and columns, drag-and-drop cards, Markdown notes
- Natural-language due dates: `Pay rent tomorrow`, `fri`, `next mon`, `in 3 days`, `oct 5`
- Today and Upcoming views across all boards

## Run locally

    uv sync
    uv run flask --app kanban run --debug

Data lives in `~/kanban-data` (override with `KANBAN_DATA_DIR`).

## Docker

    cp .env.example .env    # set PROXY_NETWORK to your reverse proxy's network
    docker compose up -d --build

The container listens on port 8000 on that network only (no published ports). There is
**no authentication**, so put it behind a proxy route restricted to your LAN or VPN.

## Develop

    uv run pytest
    uv run ruff check .
