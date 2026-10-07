#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"
umask 077
[[ -f .env ]] && { set -a; source .env; set +a; }
[[ ${#AI_SERVICE_TOKEN} -ge 32 ]] || { echo 'Set AI_SERVICE_TOKEN (32+ characters) in .env'; exit 1; }
if [[ -f ai.pid ]] && kill -0 "$(cat ai.pid)" 2>/dev/null; then echo 'AI service already running'; exit 1; fi
export WORKBENCH_DATA="$APP_DIR/data"
export EMBEDDING_CACHE="$APP_DIR/runtime/embeddings"
export PLAYWRIGHT_BROWSERS_PATH="$APP_DIR/runtime/browsers"
export PATH="$APP_DIR/runtime/node/bin:$PATH"
export QA_COMMAND
QA_COMMAND="$(node -e 'console.log(JSON.stringify([process.execPath,process.argv[1]]))' "$APP_DIR/qa/worker.mjs")"
export LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false
mkdir -p logs
nohup "$APP_DIR/runtime/ai-venv/bin/python" -m uvicorn ai_service.app:app --host 127.0.0.1 --port 18124 --workers 1 --no-access-log > logs/ai.log 2>&1 < /dev/null &
echo $! > ai.pid
echo 'AI service started on loopback port 18124'