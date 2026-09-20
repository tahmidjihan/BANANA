#!/bin/bash
# Banana Bot starter — host mode (podman/docker optional)
# Usage: ./start.sh [--port 8080] [--host 127.0.0.1] [--telegram] [--no-gui] [--mock] [--docker] [--stop] [--foreground]
# Default: host mode, GUI on :8080, Telegram off (enable with --telegram)
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PORT=8080
HOST=127.0.0.1
DO_GUI=1
DO_TG=0
DO_MOCK=0
DO_DOCKER=0
FOREGROUND=0
DO_STOP=0

for arg in "$@"; do
  case "$arg" in
    --port) shift; PORT="${1:-8080}"; shift || true ;;
    --port=*) PORT="${arg#--port=}";;
    --host) shift; HOST="${1:-127.0.0.1}"; shift || true ;;
    --host=*) HOST="${arg#--host=}";;
    --telegram|--tg) DO_TG=1 ;;
    --no-gui) DO_GUI=0 ;;
    --mock) DO_MOCK=1 ;;
    --docker) DO_DOCKER=1 ;;
    --foreground|--fg) FOREGROUND=1 ;;
    --stop) DO_STOP=1 ;;
    --help|-h) echo "Usage: $0 [--port 8080] [--host 127.0.0.1] [--telegram] [--no-gui] [--mock] [--docker] [--foreground] [--stop]"; exit 0 ;;
  esac
done
# handle --port 8080 style (shift loop above breaks, redo simple parse)
# re-parse for --port/--host with value
ARGS=("$@")
for i in "${!ARGS[@]}"; do
  if [ "${ARGS[i]}" = "--port" ] && [ -n "${ARGS[i+1]:-}" ]; then PORT="${ARGS[i+1]}"; fi
  if [ "${ARGS[i]}" = "--host" ] && [ -n "${ARGS[i+1]:-}" ]; then HOST="${ARGS[i+1]}"; fi
done

PID_GUI="/tmp/banana-gui.pid"
PID_TG="/tmp/banana-tg.pid"
LOG_DIR="$ROOT/instances/logs"
mkdir -p "$LOG_DIR" 2>/dev/null || true
if [ ! -w "$LOG_DIR" ] 2>/dev/null; then LOG_DIR="/tmp/banana-logs"; mkdir -p "$LOG_DIR"; fi

stop_one() {
  local pidfile="$1" name="$2"
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile" 2>/dev/null || echo "")
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo "stopping $name pid $pid"
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
  fi
  pkill -f "src.gui.server.*$PORT" 2>/dev/null || true
  pkill -f "src.detector.telegram" 2>/dev/null || true
}

if [ "$DO_STOP" = "1" ]; then
  stop_one "$PID_GUI" "gui"
  stop_one "$PID_TG" "telegram"
  echo "stopped"
  exit 0
fi

# auto-stop stale before start
stop_one "$PID_GUI" "gui" 2>/dev/null || true
# don't kill telegram if not starting it
if [ "$DO_TG" = "1" ]; then stop_one "$PID_TG" "telegram" 2>/dev/null || true; fi

# .env
if [ -f "$ROOT/.env" ]; then
  set -a; . "$ROOT/.env"; set +a
  echo ".env loaded (OPENCODE_MODEL=${OPENCODE_MODEL:-opencode/big-pickle})"
else
  echo "warn: .env not found, copying .env.example"
  [ -f .env.example ] && cp .env.example .env || true
fi
export OPENCODE_MODEL="${OPENCODE_MODEL:-opencode/big-pickle}"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"

# deps
if ! python3 -c "import croniter" 2>/dev/null; then
  echo "installing requirements.txt..."
  python3 -m pip install -q -r requirements.txt 2>&1 | tail -n 5 || pip install -q -r requirements.txt 2>&1 | tail -n 5 || echo "pip not available, assuming deps present (croniter, requests) or use venv"
fi

# opencode check
if ! command -v opencode >/dev/null 2>&1; then
  echo "error: opencode not found in PATH ($HOME/.opencode/bin). Install: curl -fsSL https://opencode.ai/install | bash"
  exit 1
fi
echo "opencode $(opencode --version 2>&1) model=$OPENCODE_MODEL"
if [ "$DO_MOCK" = "1" ]; then export MOCK_OPENCODE=1; echo "mock mode on (MOCK_OPENCODE=1)"; fi

# docker mode
if [ "$DO_DOCKER" = "1" ]; then
  COMPOSE=""
  if command -v docker >/dev/null 2>&1 && docker --version >/dev/null 2>&1; then COMPOSE="docker compose"
  elif command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then COMPOSE="podman compose"
  fi
  if [ -z "$COMPOSE" ]; then echo "error: --docker requested but docker/podman compose not available (host mode default)"; exit 1; fi
  echo "starting via $COMPOSE (port $PORT -> 8080)"
  if [ "$FOREGROUND" = "1" ]; then
    exec $COMPOSE run --rm -p "$PORT:8080" banana python -m src.gui.server --host 0.0.0.0 --port 8080
  else
    $COMPOSE up -d 2>&1 | tail -n 20 || $COMPOSE run -d -p "$PORT:8080" banana python -m src.gui.server --host 0.0.0.0 --port 8080
    echo "docker: http://localhost:$PORT"
    exit 0
  fi
fi

# host mode
echo "Banana host mode — GUI $HOST:$PORT  TG=$DO_TG  mock=$DO_MOCK"
echo "logs: $LOG_DIR/gui.log $LOG_DIR/telegram.log"

if [ "$DO_GUI" = "1" ]; then
  if [ "$FOREGROUND" = "1" ]; then
    echo "foreground GUI http://$HOST:$PORT (Ctrl+C to stop)"
    exec python3 -m src.gui.server --host "$HOST" --port "$PORT"
  else
    nohup python3 -m src.gui.server --host "$HOST" --port "$PORT" > "$LOG_DIR/gui.log" 2>&1 &
    echo $! > "$PID_GUI"
    sleep 1
    if kill -0 "$(cat "$PID_GUI")" 2>/dev/null; then
      echo "GUI started pid $(cat "$PID_GUI") -> http://$HOST:$PORT"
      curl -s "http://$HOST:$PORT/api/health" 2>&1 | head -n 5 || echo "health check pending..."
    else
      echo "GUI failed to start — see $LOG_DIR/gui.log"
      cat "$LOG_DIR/gui.log" | tail -n 30
      exit 1
    fi
  fi
fi

if [ "$DO_TG" = "1" ]; then
  if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then echo "warn: TELEGRAM_BOT_TOKEN empty in .env — telegram will exit"; fi
  if [ "$FOREGROUND" = "1" ] && [ "$DO_GUI" = "0" ]; then
    echo "foreground Telegram polling..."
    exec python3 -m src.detector.telegram --poll
  else
    nohup python3 -m src.detector.telegram --poll > "$LOG_DIR/telegram.log" 2>&1 &
    echo $! > "$PID_TG"
    sleep 1
    echo "Telegram polling pid $(cat "$PID_TG" 2>/dev/null || echo "?") log $LOG_DIR/telegram.log"
  fi
fi

if [ "$FOREGROUND" = "0" ]; then
  echo ""
  echo "Banana running:"
  [ "$DO_GUI" = "1" ] && echo "  GUI:      http://$HOST:$PORT  (log $LOG_DIR/gui.log, pid $PID_GUI)"
  [ "$DO_TG" = "1" ] && echo "  Telegram: polling (log $LOG_DIR/telegram.log, pid $PID_TG)"
  echo "  Health:   curl http://$HOST:$PORT/api/health"
  echo "  Chat:     curl -X POST http://$HOST:$PORT/api/chat -H 'Content-Type: application/json' -d '{\"message\":\"run echo-demo hello\"}'"
  echo "  TUI:      python3 -m src.tui  (try: run echo-demo hello --mock)"
  echo "  Stop:     $0 --stop  (or pkill -f src.gui.server)"
  echo "  Logs:     tail -f $LOG_DIR/gui.log"
fi
