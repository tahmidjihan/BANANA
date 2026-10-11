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
from src.action.runner import run_task, run_steps
from src.action.executor import execute
from src.action.instances import create_temp, create_permanent
try:
    from src.action.chats import add_message as chat_add, get_chat as chat_get
except Exception:
    chat_add=lambda *a,**kw: None
    chat_get=lambda *a,**kw: None
try:
    from src.action.memory import update_memory
except Exception:
    update_memory=lambda *a,**kw: None


def _run_once(given: dict, mock: bool = False, keep: bool = False, permanent_id: str | None = None,
             policy: str = "fail_fast") -> dict:
    # 1) snapshot tasks before (to detect creation)
    from pathlib import Path as P2
    _tasks_dir_before = P2("/app/tasks") if P2("/app/tasks").exists() else Path("tasks")
    before_tasks = set(p.name for p in _tasks_dir_before.iterdir() if p.is_dir()) if _tasks_dir_before.exists() else set()

    # 2) build prompt
    prompt = build(given)

    # 3) cli -> parse TASK
    cli_result = cli_run(prompt, mock=mock)
    task = cli_result.get("task")
    args = cli_result.get("args") or {}

    # 4) detect new tasks created by opencode via its write/shell tools (before fallback)
    _tasks_dir_after = P2("/app/tasks") if P2("/app/tasks").exists() else Path("tasks")
    after_tasks = set(p.name for p in _tasks_dir_after.iterdir() if p.is_dir()) if _tasks_dir_after.exists() else set()
    created = sorted(after_tasks - before_tasks)

    # 5) fallback: if cli didn't parse task, try hint from given text/meta — skip if task just created (avoid "create task X" -> run X with garbage args)
    if not task and not created:
        # simple heuristic: if given text contains known task name, use it
        # avoid matching "create task X" — only trigger for "run X" or bare task mention
        text = (given.get("text") or "") + " " + json.dumps(given.get("meta") or {})
        lower = text.lower()
        is_create = "create task" in lower or "make task" in lower or "new task" in lower
        if not is_create:
            from pathlib import Path as P
            tasks_dir = P("/app/tasks") if P("/app/tasks").exists() else Path("tasks")
            if tasks_dir.exists():
                for td in tasks_dir.iterdir():
                    if td.is_dir() and td.name in text:
                        # also skip if the matched name is one just created in this run
                        if td.name in created:
                            continue
                        task = td.name
                        # try extract msg after task name
                        # e.g., "run echo-demo hello" -> args msg=hello
                        after = text.split(td.name, 1)[-1].strip().split()
                        if after:
                            args = {"msg": " ".join(after)}
                        break

    # 6) execute — Phase 8: a PLAN: block means a multi-step job, which takes
    # precedence over a bare TASK line.
    steps = cli_result.get("steps") or []
    if steps:
        # validate the whole plan before running anything
        from src.cli.opencode import validate_task
        from src.action.plan import validate as validate_plan
        check = validate_plan(steps, validate_task)
        job_id = given.get("id")
        if not check["ok"]:
            from src.action import logbook
            logbook.record(
                (steps[0].get("task") if steps else ""), "error",
                job_id=job_id, source=given.get("source"), attempt=1, attempts=1,
                error=check["error"], error_kind=check["error_kind"], exit_code=1,
            )
            result = {
                "status": "error", "output": "", "error": check["error"],
                "stderr": check["error"], "exit_code": 1, "task": None,
                "error_kind": check["error_kind"], "steps": [], "plan": steps,
                "cli_raw": cli_result.get("raw_text", "")[:2000],
            }
        else:
            job = run_steps(
                check["steps"], job_id=job_id, source=given.get("source"),
                policy=policy,
            )
            job["plan"] = steps
            # flatten the last step's result into the top level so the GUI,
            # instances and chat history keep working unchanged
            last = job["steps"][-1] if job["steps"] else {}
            result = {
                "status": job["status"],
                "output": job.get("output", ""),
                "error": job.get("error", ""),
                "stderr": last.get("stderr", ""),
                "exit_code": last.get("exit_code", 0),
                "task": last.get("task"),
                "error_kind": last.get("error_kind") if job["status"] == "ok" else job["error_kind"],
                "attempts": last.get("attempts", 0),
                "job": {k: job[k] for k in ("status", "failed_at", "total_ms", "error_kind") if k in job},
                "steps": job["steps"],
                "plan": steps,
                "cli_raw": cli_result.get("raw_text", "")[:2000],
            }
    elif task:
        # Phase 7: run_task retries, classifies error_kind, logs to runs.jsonl, never raises
        result = run_task(task, args, job_id=given.get("id"), source=given.get("source"))
        result["cli_raw"] = cli_result.get("raw_text", "")[:2000]
        if created:
            result["created_tasks"] = created
            result["output"] = result.get("output","") + f"\n[created: {', '.join(created)}]"
    else:
        # No TASK — return opencode's chat response (decoded_text) as output, not raw JSONL
        chat = (cli_result.get("chat_text") or cli_result.get("decoded_text") or cli_result.get("raw_text") or "").strip()
        # fallback: take last decoded text chunk if still JSONL
        if not chat:
            chat = (cli_result.get("parsed", {}) or {}).get("chat_text", "")
        if created:
            chat = chat + f"\n\nCreated tasks: {', '.join(created)}"
        result = {
            "status": "chat" if not created else "created",
            "output": chat[:4000] if chat else "No task match. Try: run echo-demo hello or run hello-py hi",
            "error": "",
            "exit_code": 0,
            "task": None,
            "error_kind": "no_task",
            "cli_raw": cli_result.get("raw_text", "")[:2000],
            "cli_error": cli_result.get("error"),
            "chat_text": chat,
            "created_tasks": created,
        }
        if created:
            result["created_tasks"] = created

    # 5) save instance
    if permanent_id:
        inst_path = create_permanent(permanent_id, given, result)
    else:
        inst_path = create_temp(given, result, keep=keep)

    # 5b) Phase 8 — per-step trace under the instance
    if result.get("steps"):
        try:
            from src.action.runner import write_job_trace
            write_job_trace(inst_path, result["steps"])
        except Exception:
            pass

    # 6) chat awareness — append user + assistant to chat if chat_id present
    chat_id = (given.get("meta") or {}).get("chat_id")
    if chat_id:
        try:
            if not chat_get(chat_id):
                # create chat file with requested id directly
                from src.action.chats import _chat_file as _cf
                import json as _js
                from datetime import datetime, timezone as _tz
                jf=_cf(chat_id)
                if not jf.exists():
                    jf.parent.mkdir(parents=True, exist_ok=True)
                    jf.write_text(_js.dumps({"id":chat_id,"title":given.get("text","New Chat")[:40] or "New Chat","created_at":datetime.now(_tz.utc).isoformat(),"updated_at":datetime.now(_tz.utc).isoformat(),"messages":[]}, indent=2), encoding="utf-8")
            chat_add(chat_id, "user", given.get("text",""), given, None)
            chat_add(chat_id, "assistant", result.get("output","")[:4000], None, result)
        except Exception as e:
            import logging as _lg
            _lg.getLogger(__name__).warning("chat append failed %s: %s", chat_id, e)

    # 7) MEMORY.md — update recent memories (how to run tasks, recent topics, user)
    try:
        update_memory(given, result, created)
    except Exception as e:
        import logging as _lg2
        _lg2.getLogger(__name__).warning("memory update failed: %s", e)

    return {
        "given": given,
        "prompt_tokens": len(prompt) // 4,
        "cli": cli_result,
        "result": result,
        "instance": str(inst_path),
        "chat_id": chat_id,
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
                from src.action.runner import run_task as do_exec
                forced = do_exec(args.mock_task, json.loads(args.args) if args.args.strip().startswith("{") else (args.args or {"msg": "cron tick"}), job_id=given.get("id"), source="cron")
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
            forced = run_task(args.mock_task, forced_args, job_id=given.get("id"), source=args.source)
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
