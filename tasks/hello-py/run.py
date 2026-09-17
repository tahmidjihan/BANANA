#!/usr/bin/env python3
"""hello-py — WORKFLOW.md:82 simple python job"""
import json
import sys

def main():
    raw = sys.argv[1] if len(sys.argv) > 1 else ""
    if not raw and not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
    msg = raw
    # try parse JSON
    if raw.strip().startswith("{"):
        try:
            obj = json.loads(raw)
            msg = obj.get("msg") or obj.get("text") or raw
        except Exception:
            pass
    print(f"hello-py: {msg} — from python task")
    # also print JSON to stderr for structured testing
    print(json.dumps({"task": "hello-py", "input": raw}), file=sys.stderr)

if __name__ == "__main__":
    main()
