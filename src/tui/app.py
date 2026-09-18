"""TUI for Banana — instant testing without Telegram
Run: python -m src.tui  (host) or sudo docker compose run --rm banana python -m src.tui (container, need --rm -it)
Commands inside TUI: message, cron, tasks, instances, clear, help, quit
"""
import json
import sys
from pathlib import Path

from src.detector.detector import from_message, from_cron
from src.prompt.builder import build
from src.cli.opencode import run as cli_run
from src.action.executor import execute
from src.action.instances import create_temp

ROOT = Path(__file__).resolve().parents[2]

BANNER = r"""
 █▀▀█ █▀▀█ █▀▀█ █▀▀▄ █▀▀▀ █▀▀█ █▀▀█ █▀▀█  Banana Bot TUI
 █  █ █  █ █▀▀▀ █  █ █    █  █ █  █ █▀▀▀  Give Banana a job and let it get the job done.
 ▀▀▀▀ █▀▀▀ ▀▀▀▀ ▀▀▀▀ ▀▀▀▀ ▀▀▀▀ ▀▀▀▀ ▀▀▀▀  mock=free Big Pickle, no Telegram needed
"""

HELP = """
Commands:
  <text>                     Send as message (e.g. run echo-demo hello)
  /msg <text>               Same — force message
  /cron <expr> <task>       Cron trigger (e.g. /cron "*/5 * * * *" echo-demo)
  /tasks                    List tasks
  /instances                List temp/permanent instances
  /clear                    Clear screen
  /help                     This help
  /quit or /exit            Leave
Flags:
  Add --mock to use free mock opencode (no API key):  /msg hello --mock
"""

def list_tasks():
    tasks_dir = ROOT / "tasks"
    if not tasks_dir.exists():
        return "No tasks/"
    out = []
    for d in sorted(tasks_dir.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            readme = d / "README.md"
            desc = ""
            if readme.exists():
                desc = readme.read_text().splitlines()[0][:60]
            out.append(f"  - {d.name:12} {desc}")
    return "\n".join(out) or "No tasks found"

def list_instances():
    base = ROOT / "instances"
    lines = []
    for kind in ("temp", "permanent"):
        d = base / kind
        if not d.exists():
            continue
        entries = [p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith(".")]
        lines.append(f"{kind} ({len(entries)}): {', '.join(sorted(entries)[:6])}{' ...' if len(entries)>6 else ''}")
        for eid in sorted(entries)[:3]:
            ctx = d / eid / "context.json"
            if ctx.exists():
                try:
                    data = json.loads(ctx.read_text())
                    given = data.get("given", {})
                    res = data.get("result", {})
                    lines.append(f"  {eid[:8]} -> {given.get('text','')[:40]} => {res.get('output','')[:40]}")
                except Exception:
                    pass
    return "\n".join(lines) or "No instances"

def run_pipeline(text: str, source="gui", mock=False, cron_expr=None, task_ref=""):
    if cron_expr:
        given = from_cron(cron_expr, task_ref=task_ref or text)
    else:
        given = from_message(text, source=source)
    prompt = build(given)
    cli_res = cli_run(prompt, mock=mock)
    task = cli_res.get("task")
    args = cli_res.get("args") or {}
    # fallback hint like main.py: if text contains task name, use it
    if not task:
        for d in (ROOT / "tasks").iterdir():
            if d.is_dir() and d.name in text:
                task = d.name
                # extract msg after task name
                after = text.split(d.name, 1)[-1].strip()
                if after:
                    args = {"msg": after}
                break
    if task:
        result = execute(task, args)
        result["cli_raw"] = cli_res.get("raw_text","")[:800]
    else:
        result = {"status":"no_task","output":cli_res.get("raw_text","")[:800],"error":"no TASK parsed","task":None}
    inst = create_temp(given, result)
    return given, prompt, cli_res, result, inst

def repl():
    print(BANNER)
    print(HELP)
    print("Tip: type 'run echo-demo hello --mock' and press enter. Try /tasks\n")
    while True:
        try:
            raw = input("🍌 banana> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break
        if not raw:
            continue
        if raw in ("/quit", "/exit", "q", "quit", "exit"):
            print("bye")
            break
        if raw in ("/help", "help", "?"):
            print(HELP)
            continue
        if raw in ("/clear", "clear"):
            print("\033c", end="")
            print(BANNER)
            continue
        if raw.startswith("/tasks"):
            print(list_tasks())
            continue
        if raw.startswith("/instances"):
            print(list_instances())
            continue

        # parse cron
        mock = "--mock" in raw
        cron_expr = None
        task_ref = ""
        text = raw
        if raw.startswith("/cron"):
            parts = raw.split()
            # /cron "*/5 * * * *" echo-demo --mock
            # naive parse: find quoted expr
            import re
            m = re.search(r'"([^"]+)"|\'([^\']+)\'', raw)
            if m:
                cron_expr = m.group(1) or m.group(2)
                after = raw[m.end():].strip().split()
                if after:
                    task_ref = after[0]
                    if task_ref == "--mock":
                        task_ref = ""
                text = task_ref
            else:
                print("usage: /cron \"*/5 * * * *\" <task> [--mock]")
                continue
        elif raw.startswith("/msg"):
            text = raw[4:].strip().replace(" --mock","").replace("--mock","").strip()
        else:
            # strip --mock flag from text for display
            text = raw.replace(" --mock","").replace("--mock","").strip()

        try:
            given, prompt, cli_res, result, inst = run_pipeline(text, mock=mock, cron_expr=cron_expr, task_ref=task_ref)
            # display
            print(f"\n[GIVEN] {given['source']} id={given['id'][:8]} text={given['text']}")
            print(f"[PROMPT] ~{len(prompt)//4} tokens")
            print(f"[CLI] task={cli_res.get('task')} args={cli_res.get('args')} exit={cli_res.get('exit_code')}")
            if cli_res.get("raw_text"):
                # truncate raw
                raw_out = cli_res['raw_text'][:600].replace("\n"," | ")
                print(f"      raw: {raw_out}")
            print(f"[ACTION] {result.get('task')} status={result.get('status')} output={result.get('output')}")
            if result.get("error"):
                print(f"         error: {result['error']}")
            print(f"[INSTANCE] {inst}  (/instances/temp/{inst.name}/context.json)")
            print()
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)

if __name__ == "__main__":
    repl()
