#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PG="$APP_DIR/runtime/postgresql/bin/pg_ctl"
DATA="$APP_DIR/data/postgresql"
[[ -x "$PG" && -f "$DATA/PG_VERSION" ]] || { echo 'Private PostgreSQL is not initialized'; exit 1; }
if "$PG" -D "$DATA" status >/dev/null 2>&1; then echo 'Private PostgreSQL is already running'; exit 0; fi
umask 077
"$PG" -D "$DATA" -l "$APP_DIR/logs/postgresql.log" -w start