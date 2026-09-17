"""CLI for action — quick manual test
python -m src.action --task echo-demo --args '{"msg":"hi"}'
python -m src.action --task hello-py --args '{"msg":"hi"}' --temp
"""
import argparse
import json
from pathlib import Path

from .executor import execute
from .instances import create_temp, reap_temp


def main():
    p = argparse.ArgumentParser(description="Banana action executor")
    p.add_argument("--task", required=True, help="task name")
    p.add_argument("--args", default="", help="JSON args or string")
    p.add_argument("--temp", action="store_true", help="create temp instance")
    p.add_argument("--reap", action="store_true", help="run reaper")
    p.add_argument("--dry-run", action="store_true", help="dry run for reap")
    args = p.parse_args()

    if args.reap:
        removed = reap_temp(dry_run=args.dry_run)
        print(f"reaped: {removed}")
        return

    # parse args
    try:
        parsed = json.loads(args.args) if args.args.strip().startswith("{") else args.args
    except Exception:
        parsed = args.args

    result = execute(args.task, parsed)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if args.temp:
        from src.detector.detector import from_message
        given = from_message(f"run {args.task}", source="gui")
        path = create_temp(given, result)
        print(f"instance: {path}", flush=True)


if __name__ == "__main__":
    main()
