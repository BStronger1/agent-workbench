#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$APP_DIR/run.pid" ]] || { echo 'No PID file'; exit 0; }
pid="$(cat "$APP_DIR/run.pid")"
[[ "$pid" =~ ^[0-9]+$ ]] || { echo 'Invalid PID'; exit 1; }
if kill -0 "$pid" 2>/dev/null; then
  command="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
  [[ "$command" == *"$APP_DIR/app.jar"* ]] || { echo 'PID does not belong to this workbench; refusing to stop.'; exit 1; }
  kill "$pid"
  for i in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  kill -0 "$pid" 2>/dev/null && { echo 'Process still stopping; inspect before retrying.'; exit 1; }
fi
rm -f -- "$APP_DIR/run.pid"
echo 'Stopped.'
