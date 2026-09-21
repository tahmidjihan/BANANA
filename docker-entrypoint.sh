#!/bin/bash
set -e
# Banana single-container entrypoint — plug & play
# Runs GUI + Telegram polling inside one container
# Usage: docker run -p 4242:4242 -v ./config/creds.json:/app/config/creds.json banana  # 4242 = 42×101 double Answer
#        docker compose up --build  # -> http://localhost:4242 + /brutal-minimalist-design

PORT="${PORT:-4242}"
HOST="${HOST:-0.0.0.0}"

# ensure creds.json exists (copy example if missing)
if [ ! -f /app/config/creds.json ] && [ -f /app/config/creds.example.json ]; then
  echo "[entrypoint] creds.json missing, copying example"
  cp /app/config/creds.example.json /app/config/creds.json
fi

# ensure instances dirs
mkdir -p /app/instances/temp /app/instances/chats /app/instances/logs 2>/dev/null || true

# load creds into env if present (jq if available, else python)
if [ -f /app/config/creds.json ] && command -v python3 >/dev/null 2>&1; then
  eval "$(python3 -c "import json,os; d=json.load(open('/app/config/creds.json')); print('\n'.join(f'export {k}={repr(v)}' for k,v in d.items()))" 2>/dev/null)" || true
fi

# also load .env if present
if [ -f /app/.env ]; then
  set -a; . /app/.env 2>/dev/null || true; set +a
fi

# opencode check
if ! command -v opencode >/dev/null 2>&1; then
  echo "[entrypoint] opencode not found, trying /root/.opencode/bin/opencode"
  export PATH="/root/.opencode/bin:$PATH"
fi
echo "[entrypoint] opencode $(opencode --version 2>&1 | head -n1) model=${OPENCODE_MODEL:-opencode/big-pickle}"

# decide what to run
MODE="${1:-gui}"

if [ "$MODE" = "gui" ] || [ "$MODE" = "all" ]; then
  # if telegram token present, start polling in background
  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ "$MODE" = "all" ]; then
    echo "[entrypoint] starting Telegram polling in background"
    python3 -m src.detector.telegram --poll > /app/instances/logs/telegram.log 2>&1 &
    echo "[entrypoint] telegram pid $!"
  elif [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
    # auto-start telegram alongside GUI unless explicitly disabled with NO_TELEGRAM=1
    if [ "${NO_TELEGRAM:-0}" != "1" ]; then
      echo "[entrypoint] Telegram token found, starting polling (set NO_TELEGRAM=1 to disable)"
      python3 -m src.detector.telegram --poll > /app/instances/logs/telegram.log 2>&1 &
    fi
  fi
  echo "[entrypoint] starting GUI on $HOST:$PORT — 4242 = 42×101 double Answer (Hitchhiker's 42), not 8080, brutal doubled"
  exec python3 -m src.gui.server --host "$HOST" --port "$PORT"
elif [ "$MODE" = "telegram" ]; then
  exec python3 -m src.detector.telegram --poll
elif [ "$MODE" = "bash" ] || [ "$MODE" = "shell" ]; then
  exec bash "${@:2}"
else
  # pass through any command (e.g., python -m src.main --message "hi")
  exec "$@"
fi
