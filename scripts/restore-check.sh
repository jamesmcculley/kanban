#!/bin/sh
# Prove a backup opens with the app's own loader, in a scratch copy (never the live data).
#   ./scripts/restore-check.sh ~/backups/trellis/kanban-YYYYMMDD-HHMMSS.tar.gz
# Needs the app image (built by `docker compose build`). Exits non-zero if the backup is corrupt.
set -eu
[ $# -eq 1 ] || { echo "usage: $0 BACKUP.tar.gz" >&2; exit 2; }
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir "$work/data"
tar xzf "$1" -C "$work/data"            # a truncated or corrupt archive fails here, loudly
docker compose run --rm --no-deps -T -v "$work/data:/restore:ro" --entrypoint python kanban \
  -m kanban.restore_check /restore
