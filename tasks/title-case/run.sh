#!/bin/bash
# title-case — converts msg to title case
# Inputs: $1 JSON {"msg":"..."} or plain args
# Outputs: title-cased text to stdout
set -e
ARGS="$*"
if [ -n "$1" ] && echo "$1" | grep -q "^{"; then
  if command -v jq >/dev/null 2>&1; then
    MSG=$(echo "$1" | jq -r '.msg // .text // empty' 2>/dev/null || echo "$1")
  elif command -v python3 >/dev/null 2>&1; then
    MSG=$(echo "$1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('msg', d.get('text','')) if isinstance(d,dict) else d)" 2>/dev/null || echo "$1")
  else
    MSG="$1"
  fi
else
  MSG="$ARGS"
fi
if command -v python3 >/dev/null 2>&1; then
  echo "$MSG" | python3 -c "import sys; print(sys.stdin.read().strip().title())"
else
  echo "$MSG" | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2))}1'
fi
