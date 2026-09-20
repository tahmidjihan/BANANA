"""Main glue — WORKFLOW.md:97, plan.md:204-223
detector -> prompt builder -> cli (opencode) -> action -> save instance -> print result
Supports: --message, --cron + --task, --cron-mode (single tick or loop)
"""
import argparse
import json
import sys
import time
from pathlib import Path

from src.detector.detector import from_cron, from_message
from src.prompt.builder import build
from src.cli.opencode import run as cli_run
from src.action.executor import execute
from src.action.instances import create_temp, create_permanent


def _run_once(given: dict, mock: bool = False, keep: bool = False, permanent_id: str | None = None) -> dict:
    # 1) build prompt
    prompt = build(given)

    # 2) cli -> parse TASK
    cli_result = cli_run(prompt, mock=mock)
    task = cli_result.get("task")
    args = cli_result.get("args") or {}

    # 3) fallback: if cli didn't parse task, try hint from given text/meta
    if not task:
        # simple heuristic: if given text contains known task name, use it
        text = (given.get("text") or "") + " " + json.dumps(given.get("meta") or {})
        from pathlib import Path as P
        tasks_dir = P("/app/tasks") if P("/app/tasks").exists() else Path("tasks")
        if tasks_dir.exists():
            for td in tasks_dir.iterdir():
                if td.is_dir() and td.name in text:
                    task = td.name
                    # try extract msg after task name
                    # e.g., "run echo-demo hello" -> args msg=hello
                    after = text.split(td.name, 1)[-1].strip().split()
                    if after:
                        args = {"msg": " ".join(after)}
                    break

    # 4) execute if task found
    if task:
        result = execute(task, args)
        result["cli_raw"] = cli_result.get("raw_text", "")[:2000]
    else:
        # No TASK — return opencode's chat response (decoded_text) as output, not raw JSONL
        chat = (cli_result.get("chat_text") or cli_result.get("decoded_text") or cli_result.get("raw_text") or "").strip()
        # fallback: take last decoded text chunk if still JSONL
        if not chat:
            chat = (cli_result.get("parsed", {}) or {}).get("chat_text", "")
        result = {
            "status": "chat",
            "output": chat[:4000] if chat else "No task match. Try: run echo-demo hello or run hello-py hi",
            "error": "",
            "exit_code": 0,
            "task": None,
            "cli_raw": cli_result.get("raw_text", "")[:2000],
            "cli_error": cli_result.get("error"),
            "chat_text": chat,
        }

    # 5) save instance
    if permanent_id:
        inst_path = create_permanent(permanent_id, given, result)
    else:
        inst_path = create_temp(given, result, keep=keep)

    return {
        "given": given,
        "prompt_tokens": len(prompt) // 4,
        "cli": cli_result,
        "result": result,
        "instance": str(inst_path),
    }


def main():
    p = argparse.ArgumentParser(description="Banana main pipeline")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--message", type=str, help="user message")
    g.add_argument("--cron", type=str, help="cron expr, e.g. '*/5 * * * *'")
    g.add_argument("--cron-mode", action="store_true", help="cron loop mode (requires --cron)")
    p.add_argument("--task", type=str, default="", help="task_ref for --cron")
    p.add_argument("--source", type=str, default="gui", choices=["gui", "telegram", "cron"])
    p.add_argument("--mock", action="store_true", help="use mock opencode")
    p.add_argument("--mock-task", type=str, default="", help="force mock TASK name (e.g. echo-demo)")
    p.add_argument("--args", type=str, default="", help="override args JSON for mock-task")
    p.add_argument("--keep", action="store_true", help="keep temp instance from reaper")
    p.add_argument("--permanent-id", type=str, default="", help="save as permanent instance id")
    p.add_argument("--json", action="store_true", help="output JSON")
    p.add_argument("--loop", action="store_true", help="with --cron-mode, loop forever (60s tick)")
    p.add_argument("--once", action="store_true", help="with --cron-mode, run single tick then exit")
    args = p.parse_args()

    # handle cron-mode
    if args.cron_mode or args.cron:
        # cron-mode branch
        cron_expr = args.cron if args.cron else None
        if args.cron_mode and not cron_expr:
            print("error: --cron-mode requires --cron 'expr'", file=sys.stderr)
            sys.exit(1)
        # loop or once
        def tick():
            given = from_cron(cron_expr, task_ref=args.task)
            # optionally force mock task
            out = _run_once(given, mock=args.mock, keep=args.keep, permanent_id=args.permanent_id or None)
            # inject mock-task if needed for testing without real LLM
            if args.mock_task and out["result"].get("status") == "no_task":
                from src.action.executor import execute as do_exec
                forced = do_exec(args.mock_task, json.loads(args.args) if args.args.strip().startswith("{") else (args.args or {"msg": "cron tick"}))
                # overwrite result and recreate instance with forced result
                # (simpler: just run forced and update)
                out["result"] = forced
                # update instance
                from src.action.instances import create_temp as ct
                # note: we lose original instance; create new one with forced
                given2 = from_cron(cron_expr, task_ref=args.mock_task)
                inst = ct(given2, forced, keep=args.keep)
                out["instance"] = str(inst)
                out["given"] = given2
            if args.json:
                print(json.dumps(out, indent=2, ensure_ascii=False))
            else:
                print(json.dumps(out, indent=2, ensure_ascii=False))
                print(f"\n[TICK] {given['id']} -> {out['result'].get('task')} status={out['result'].get('status')}", file=sys.stderr)
            return out

        if args.loop:
            print(f"cron-mode loop: {cron_expr} task={args.task} every 60s", file=sys.stderr)
            while True:
                # check if cron due using croniter? MVP: just tick every 60s
                tick()
                time.sleep(60)
        else:
            tick()
        return

    # message branch
    if args.message is not None:
        given = from_message(args.message, source=args.source)
        out = _run_once(given, mock=args.mock, keep=args.keep, permanent_id=args.permanent_id or None)
        # mock-task override
        if args.mock_task:
            forced_args = json.loads(args.args) if args.args.strip().startswith("{") else (args.args or {"msg": "hello"})
            forced = execute(args.mock_task, forced_args)
            out["result"] = forced
            # update instance to reflect forced
            given2 = from_message(f"run {args.mock_task} {forced_args}", source=args.source)
            inst = create_temp(given2, forced, keep=args.keep)
            out["instance"] = str(inst)
            out["given"] = given2
        if args.json:
            print(json.dumps(out, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(out, indent=2, ensure_ascii=False))
            print(f"\n[MAIN] {given['id']} -> {out['result'].get('task')} output={out['result'].get('output')}", file=sys.stderr)


if __name__ == "__main__":
    main()
