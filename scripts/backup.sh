#!/bin/sh
# Snapshot the kanban data volume to a timestamped .tar.gz and keep the newest $KEEP.
# Run from cron/systemd on the Docker host. Needs GNU xargs (-r); fine on Linux.
#
#   KANBAN_CONTAINER  container name             (default: kanban)
#   BACKUP_DIR        where tarballs are written (default: ~/kanban-backups)
#   KEEP              how many to retain         (default: 14)
#
# Restore: docker exec -i kanban tar xzf - -C /data < kanban-YYYYMMDD-HHMMSS.tar.gz
set -eu

container="${KANBAN_CONTAINER:-kanban}"
dest="${BACKUP_DIR:-$HOME/kanban-backups}"
keep="${KEEP:-14}"

mkdir -p "$dest"
out="$dest/kanban-$(date +%Y%m%d-%H%M%S).tar.gz"

docker exec "$container" tar czf - -C /data . > "$out.tmp"
tar tzf "$out.tmp" > /dev/null          # refuse to keep a corrupt archive
mv "$out.tmp" "$out"

ls -1t "$dest"/kanban-*.tar.gz | tail -n +"$((keep + 1))" | xargs -r rm --
echo "backup ok: $out"
