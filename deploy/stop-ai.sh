#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"
[[ -f ai.pid ]] || exit 0
pid="$(cat ai.pid)"
[[ "$pid" =~ ^[0-9]+$ ]] || exit 1
[[ "$(readlink -f "/proc/$pid/cwd")" == "$APP_DIR" ]] || { echo 'PID directory mismatch'; exit 1; }
tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q 'uvicorn ai_service.app:app' || { echo 'PID command mismatch'; exit 1; }
kill "$pid"
rm ai.pid