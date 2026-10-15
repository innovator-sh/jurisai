#!/usr/bin/env bash
# Nightly MongoDB backup for the single-VM deployment (plan: "back up the Mongo
# volume on a cron job regardless"). Dumps the jurisai database to a gzip
# archive under $BACKUP_DIR and deletes archives older than
# $BACKUP_RETENTION_DAYS (default 14) -- keep that equal to BACKUP_RETENTION_DAYS
# in .env, because /privacy tells users that is how long a deleted account can
# linger in a backup.
#
#   crontab -e:   17 2 * * *  /opt/jurisai/scripts/backup_mongo.sh >> /var/log/jurisai-backup.log 2>&1
#
# Backups contain personal data (emails, chats): keep BACKUP_DIR on the VM,
# readable by root only. Copying them off the VM to a foreign cloud would
# undo the India-only data posture -- do not.
set -euo pipefail

cd "$(dirname "$0")/.."
BACKUP_DIR="${BACKUP_DIR:-/var/backups/jurisai}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

umask 077
mkdir -p "$BACKUP_DIR"
out="$BACKUP_DIR/jurisai-$(date -u +%Y-%m-%dT%H%M%SZ).archive.gz"

"${COMPOSE[@]}" exec -T mongo mongodump --db jurisai --archive --gzip > "$out"

# An empty/truncated archive must fail the job loudly, not look like success.
if [ ! -s "$out" ]; then
  echo "backup FAILED: $out is empty" >&2
  rm -f "$out"
  exit 1
fi

find "$BACKUP_DIR" -name 'jurisai-*.archive.gz' -mtime +"$RETENTION_DAYS" -delete
echo "backup ok: $out ($(du -h "$out" | cut -f1)); pruned archives older than ${RETENTION_DAYS}d"
