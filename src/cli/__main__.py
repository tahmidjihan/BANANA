"""CLI — WORKFLOW.md:67
python -m src.cli --prompt "hello" [--mock] [--prompt-file file]
"""
import argparse
import json
import sys
from pathlib import Path

from .opencode import run


def main():
    p = argparse.ArgumentParser(description="Banana opencode wrapper")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--prompt", type=str, help="prompt string")
    g.add_argument("--prompt-file", type=str, help="read prompt from file")
    g.add_argument("--given-file", type=str, help="Given JSON -> build prompt first")
    p.add_argument("--mock", action="store_true", help="use mock without calling opencode")
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--json", action="store_true", help="output JSON")
    args = p.parse_args()

    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    elif args.given_file:
        from src.prompt.builder import build
        given = json.loads(Path(args.given_file).read_text(encoding="utf-8"))
        prompt = build(given)
    else:
        prompt = args.prompt

    result = run(prompt, timeout=args.timeout, mock=args.mock)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result["raw_text"])
        if result["error"]:
            print(f"error: {result['error']}", file=sys.stderr)
        if result["task"]:
            print(f"\nParsed TASK: {result['task']} ARGS: {result['args']}", file=sys.stderr)


if __name__ == "__main__":
    main()
