#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"
[[ -f ai.pid ]] || exit 0
pid="$(cat ai.pid)"
[[ "$pid" =~ ^[0-9]+$ ]] || exit 1
if ! kill -0 "$pid" 2>/dev/null; then rm -- ai.pid; exit 0; fi
[[ "$(readlink -f "/proc/$pid/cwd")" == "$APP_DIR" ]] || { echo 'PID directory mismatch'; exit 1; }
tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q 'uvicorn ai_service.app:app' || { echo 'PID command mismatch'; exit 1; }
kill "$pid"
for i in $(seq 1 30); do
  kill -0 "$pid" 2>/dev/null || break
  sleep 1
done
kill -0 "$pid" 2>/dev/null && { echo 'AI service is still stopping; inspect before restarting'; exit 1; }
rm -- ai.pid