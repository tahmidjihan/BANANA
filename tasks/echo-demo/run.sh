#!/bin/bash
# echo-demo — WORKFLOW.md:81 tasks/echo-demo/run.sh
# Inputs: args as JSON in $1 or stdin, or plain args
# Outputs: echo args to stdout
set -e
ARGS="$*"
if [ -n "$1" ] && echo "$1" | grep -q "^{"; then
  # JSON args — try jq if available else raw
  if command -v jq >/dev/null 2>&1; then
    MSG=$(echo "$1" | jq -r '.msg // .text // .args // empty' 2>/dev/null || echo "$1")
  else
    MSG="$1"
  fi
  echo "echo-demo: $MSG"
else
  echo "echo-demo: $ARGS"
fi
# also echo structured JSON to stderr for testing
echo "{\"task\":\"echo-demo\",\"input\":\"$ARGS\"}" >&2 || true
