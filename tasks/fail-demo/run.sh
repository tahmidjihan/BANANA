#!/usr/bin/env bash
# fail-demo — WORKFLOW.md Phase 7 test task
# Always fails. Exists to prove retry + error_kind + run-log work.
# args: {"code": 3}
set -uo pipefail

ARGS="${1:-}"
CODE=1
if [ -n "$ARGS" ]; then
  v=$(echo "$ARGS" | python3 -c 'import sys,json
try: print(int(json.load(sys.stdin).get("code",1)))
except Exception: print(1)' 2>/dev/null || echo 1)
  CODE="${v:-1}"
fi

echo "fail-demo: failing on purpose with exit code ${CODE}" >&2
exit "$CODE"