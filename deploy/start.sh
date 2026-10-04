#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"
umask 077
mkdir -p data logs
if [[ -f run.pid ]] && kill -0 "$(cat run.pid)" 2>/dev/null; then
  echo "A recorded process is already running; inspect it before restarting."
  exit 1
fi
if [[ -f .env ]]; then set -a; source .env; set +a; fi
export WORKBENCH_DATA="$APP_DIR/data"
export PORT="${PORT:-18123}"
export BIND_ADDRESS="${BIND_ADDRESS:-127.0.0.1}"
export WORKBENCH_MODE="${WORKBENCH_MODE:-demo}"
export PLAYWRIGHT_BROWSERS_PATH="$APP_DIR/runtime/browsers"
export PATH="$APP_DIR/runtime/node/bin:$PATH"
export QA_COMMAND
QA_COMMAND="$(node -e 'console.log(JSON.stringify([process.execPath,process.argv[1]]))' "$APP_DIR/qa/worker.mjs")"
if [[ "$WORKBENCH_MODE" == live ]]; then
  LIVE_ACCESS_TOKEN="${LIVE_ACCESS_TOKEN:-}"
  if [[ -z "${LLM_API_KEY:-}" || ${#LIVE_ACCESS_TOKEN} -lt 24 ]]; then echo 'Live mode needs an API key and a 24+ character access token.'; exit 1; fi
fi
nohup "$APP_DIR/runtime/jre/bin/java" -Xms128m -Xmx768m -jar "$APP_DIR/app.jar" > "$APP_DIR/logs/server.log" 2>&1 < /dev/null &
echo $! > run.pid
echo "Started Agent Workbench on port $PORT (PID $(cat run.pid))."
