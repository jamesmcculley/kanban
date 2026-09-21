#!/usr/bin/env bash
# One-command deploy. Run on the host from this repo: back up live data, pull, rebuild, restart.
# (Standard 04; the whole body is a function so `git pull` rewriting this file cannot confuse bash.)
set -euo pipefail

main() {
  cd "$(dirname "$0")"

  BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/trellis}" ./scripts/backup.sh

  echo "Pulling latest..."
  git pull --ff-only origin main
  APP_VERSION="$(git rev-parse --short HEAD)"
  export APP_VERSION

  echo "Rebuilding and restarting..."
  docker compose up -d --build

  echo "Deployed $APP_VERSION"
}

main "$@"
exit
