#!/usr/bin/env bash
# slow-demo — WORKFLOW.md Phase 7 test task
# Sleeps longer than its meta.json timeout, to prove timeout classification.
# args: {"sleep": 30}
set -uo pipefail

ARGS="${1:-}"
SLEEP=30
if [ -n "$ARGS" ]; then
  v=$(echo "$ARGS" | python3 -c 'import sys,json
try: print(int(json.load(sys.stdin).get("sleep",30)))
except Exception: print(30)' 2>/dev/null || echo 30)
  SLEEP="${v:-30}"
fi

echo "slow-demo: sleeping ${SLEEP}s"
sleep "$SLEEP"
echo "slow-demo: done"