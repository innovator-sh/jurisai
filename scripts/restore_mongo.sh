#!/usr/bin/env bash
# Restore a backup made by backup_mongo.sh:  scripts/restore_mongo.sh <archive.gz>
# Replaces the live jurisai database (--drop), so it asks first.
set -euo pipefail

[ $# -eq 1 ] && [ -f "$1" ] || { echo "usage: $0 <archive.gz>" >&2; exit 2; }
cd "$(dirname "$0")/.."

read -r -p "This DROPS and replaces the live 'jurisai' database with $1. Type 'restore' to continue: " answer
[ "$answer" = "restore" ] || { echo "aborted"; exit 1; }

docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T mongo \
  mongorestore --drop --archive --gzip < "$1"
echo "restore complete"
