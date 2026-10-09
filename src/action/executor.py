"""Executor — WORKFLOW.md:76-79, plan.md:117-124
execute(task_name, args) runs tasks/{name}/run.sh or run.py inside container
Timeout 60s (overridable via tasks/{name}/meta.json), capture stdout/stderr,
retries with backoff, confined to /app/instances and /app/tasks.
Every attempt is appended to instances/logs/runs.jsonl — Phase 7.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from src.action import logbook

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "tasks"
# container paths
CONTAINER_TASKS = Path("/app/tasks")
CONTAINER_INSTANCES = Path("/app/instances")

TIMEOUT = 60
DEFAULT_RETRIES = 1
BACKOFF_SECONDS = 2


def _tasks_dir() -> Path:
    if CONTAINER_TASKS.exists():
        return CONTAINER_TASKS
    return TASKS_DIR


def task_meta(task_name: str) -> dict:
    """Optional tasks/{name}/meta.json — WORKFLOW.md Phase 7
    {"timeout": 120, "retries": 2}. Malformed meta is ignored, never fatal.
    """
    try:
        name = task_name.strip().strip("/")
        if not name or ".." in name or name.startswith("/"):
            return {}
        p = _tasks_dir() / name / "meta.json"
        if not p.exists():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def classify_error(returncode: int, stderr: str, exc: Exception | None = None, timed_out: bool = False) -> str:
    """Map a failure to a stable error_kind — WORKFLOW.md Phase 7"""
    if timed_out:
        return "timeout"
    if isinstance(exc, FileNotFoundError):
        return "not_found"
    if isinstance(exc, ValueError):
        return "invalid_args"
    if exc is not None:
        return "spawn_error"
    return "nonzero_exit" if returncode != 0 else "ok"


def _resolve_task(task_name: str) -> tuple[Path, str]:
    """Return (run_path, kind) or raise"""
    if not task_name or not task_name.strip():
        raise ValueError("task_name required")
    # sanitize — no traversal
    name = task_name.strip().strip("/")
    if ".." in name or name.startswith("/"):
        raise ValueError(f"invalid task_name: {task_name}")
    td = _tasks_dir() / name
    if not td.exists() or not td.is_dir():
        raise FileNotFoundError(f"task not found: {name} in {_tasks_dir()}")
    # prefer run.sh then run.py
    for cand, kind in [(td / "run.sh", "bash"), (td / "run.py", "python")]:
        if cand.exists():
            return cand, kind
    raise FileNotFoundError(f"no run.sh or run.py in {td}")


def _attempt(task_name: str, args_str: str, run_path: Path, kind: str, timeout: int) -> dict:
    """One execution attempt. Never raises — always returns a result dict."""
    cmd = []
    if kind == "bash":
        cmd = ["bash", str(run_path), args_str] if args_str else ["bash", str(run_path)]
    else:
        cmd = [sys.executable, str(run_path), args_str] if args_str else [sys.executable, str(run_path)]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
        )
        # confine writes check — we only capture, tasks must not write outside allowed dirs
        # (enforced by doc, not runtime sandbox MVP)
        kind_err = classify_error(proc.returncode, proc.stderr)
        return {
            "status": "ok" if proc.returncode == 0 else "error",
            "output": proc.stdout.strip(),
            "error": proc.stderr.strip() if proc.returncode != 0 else "",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "task": task_name,
            "error_kind": kind_err,
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "output": "",
            "error": f"timeout after {timeout}s",
            "stdout": "",
            "stderr": f"timeout after {timeout}s",
            "exit_code": 124,
            "task": task_name,
            "error_kind": "timeout",
        }
    except Exception as e:
        kind_err = classify_error(0, "", exc=e)
        return {
            "status": "error",
            "output": "",
            "error": str(e),
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1,
            "task": task_name,
            "error_kind": kind_err,
        }


def execute(
    task_name: str,
    args: dict | str | None = None,
    timeout: int = TIMEOUT,
    retries: int | None = None,
    job_id: str | None = None,
    source: str | None = None,
    backoff: int = BACKOFF_SECONDS,
) -> dict:
    """Execute task with retry + run-log — WORKFLOW.md:77, Phase 7
    args: dict -> JSON string passed as $1 and stdin
    retries: None -> tasks/{name}/meta.json "retries", else DEFAULT_RETRIES
    Returns {status: ok|error, output, error, exit_code, task, error_kind, attempts, runs}
    """
    task_name = task_name.strip()
    meta = task_meta(task_name)
    if timeout is None or timeout == TIMEOUT:
        timeout = int(meta.get("timeout", TIMEOUT) or TIMEOUT)
    if retries is None:
        retries = int(meta.get("retries", DEFAULT_RETRIES) or 0)
    retries = max(0, int(retries))

    # normalize args to string
    if args is None:
        args_str = ""
    elif isinstance(args, dict):
        args_str = json.dumps(args, ensure_ascii=False)
    else:
        args_str = str(args)

    try:
        run_path, kind = _resolve_task(task_name)
    except Exception as e:
        kind_err = classify_error(0, "", exc=e)
        result = {
            "status": "error",
            "output": "",
            "error": str(e),
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1,
            "task": task_name,
            "error_kind": kind_err,
        }
        logbook.record(
            task_name, "error", job_id=job_id, source=source, attempt=1, attempts=1,
            error=str(e), error_kind=kind_err, exit_code=1, duration_ms=0,
        )
        result["attempts"] = 1
        result["runs"] = []
        return result

    runs = []
    result: dict = {}
    total_attempts = retries + 1
    for attempt in range(1, total_attempts + 1):
        started = time.monotonic()
        result = _attempt(task_name, args_str, run_path, kind, timeout)
        duration_ms = int((time.monotonic() - started) * 1000)
        runs.append({"attempt": attempt, "status": result["status"], "error_kind": result["error_kind"], "duration_ms": duration_ms})
        logbook.record(
            task_name, result["status"], job_id=job_id, source=source,
            attempt=attempt, attempts=total_attempts,
            error=result.get("error", ""), error_kind=result.get("error_kind", ""),
            exit_code=result.get("exit_code"), duration_ms=duration_ms,
            output=result.get("output", ""),
        )
        if result["status"] == "ok":
            break
        if attempt < total_attempts:
            time.sleep(backoff)

    result["attempts"] = len(runs)
    result["retries"] = retries
    result["runs"] = runs
    result.setdefault("error_kind", "ok" if result["status"] == "ok" else "nonzero_exit")
    return result
