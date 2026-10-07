#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
"$APP_DIR/runtime/postgresql/bin/pg_ctl" -D "$APP_DIR/data/postgresql" -m fast -w stop