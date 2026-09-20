#!/bin/bash
# count-words — counts words in msg
# Inputs: $1 JSON {"msg":"..."} or plain args
# Outputs: word count to stdout
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
# trim and count words (wc -w handles multiple spaces/newlines)
if [ -z "$(echo "$MSG" | tr -d '[:space:]')" ]; then
  echo "0"
else
  echo "$MSG" | wc -w | tr -d ' '
fi
