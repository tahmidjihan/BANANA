"""CLI — WORKFLOW.md:36
python -m src.detector --message "do X" [--source gui|telegram]
python -m src.detector --cron "*/5 * * * *" --task echo-demo
"""
import argparse
import json
import sys

from .detector import from_cron, from_message, to_json


def main():
    p = argparse.ArgumentParser(description="Banana Detector — Given builder")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--message", type=str, help="user message text")
    g.add_argument("--cron", type=str, help="cron expression, e.g. '*/5 * * * *'")

    p.add_argument("--source", type=str, default="gui", choices=["gui", "telegram", "cron"], help="source for --message")
    p.add_argument("--task", type=str, default="", help="task_ref for --cron")
    p.add_argument("--out", type=str, default="", help="write Given JSON to file")
    p.add_argument("--pretty", action="store_true", default=True, help="pretty print")
    p.add_argument("--compact", action="store_true", help="compact JSON")

    args = p.parse_args()
    pretty = not args.compact

    try:
        if args.message is not None:
            given = from_message(args.message, source=args.source)
        else:
            given = from_cron(args.cron, task_ref=args.task)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    out = to_json(given, pretty=pretty)
    print(out)

    if args.out:
        from pathlib import Path
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"written to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
