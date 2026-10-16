#!/usr/bin/env bash
# Free uptime check (cron + curl) for when an external monitor isn't wanted.
# Hits /readyz, which fails if Mongo is down or a corpus index is missing --
# a stronger signal than /healthz (process is up). Exits non-zero on failure
# so cron/MAILTO or a wrapper can alert, and logs one line per run.
#
#   crontab -e:   */5 * * * *  /opt/jurisai/scripts/uptime_check.sh https://your.domain >> /var/log/jurisai-uptime.log 2>&1
#
# An external monitor (UptimeRobot's free tier pointed at /readyz) is the
# better option when available: it still works when this whole VM is down.
set -uo pipefail

url="${1:?usage: $0 https://your.domain}"
now="$(date -u +%FT%TZ)"

if body="$(curl --fail --silent --show-error --max-time 10 "${url%/}/readyz" 2>&1)"; then
  echo "$now OK $url"
else
  echo "$now FAIL $url :: ${body:0:200}" >&2
  exit 1
fi
