"""CLI — WORKFLOW.md:51
Feed Phase 1 Given -> inspect built prompt output
"""
import argparse
import json
import sys
from pathlib import Path

from .builder import build


def main():
    p = argparse.ArgumentParser(description="Banana Prompt Builder")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--message", type=str, help="inline message text")
    g.add_argument("--given-file", type=str, help="path to Given JSON")
    g.add_argument("--given-json", type=str, help="inline Given JSON")
    g.add_argument("--cron", type=str, help="cron expr with --task for Given")
    p.add_argument("--task", type=str, default="", help="task_ref for --cron")
    p.add_argument("--out", type=str, default="", help="write prompt to file")
    p.add_argument("--source", type=str, default="gui", choices=["gui", "telegram", "cron"])
    args = p.parse_args()

    # Build Given dict
    given = None
    if args.given_file:
        given = json.loads(Path(args.given_file).read_text(encoding="utf-8"))
    elif args.given_json:
        given = json.loads(args.given_json)
    elif args.cron is not None:
        from src.detector.detector import from_cron
        given = from_cron(args.cron, task_ref=args.task)
    elif args.message:
        from src.detector.detector import from_message
        given = from_message(args.message, source=args.source)

    if not given:
        print("no Given built", file=sys.stderr)
        sys.exit(1)

    prompt = build(given)
    print(prompt)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(prompt, encoding="utf-8")
        print(f"\nwritten to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
