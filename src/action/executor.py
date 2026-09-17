"""Executor — WORKFLOW.md:76-79, plan.md:117-124
execute(task_name, args) runs tasks/{name}/run.sh or run.py inside container
Timeout 60s, capture stdout/stderr, confined to /app/instances and /app/tasks
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "tasks"
# container paths
CONTAINER_TASKS = Path("/app/tasks")
CONTAINER_INSTANCES = Path("/app/instances")

TIMEOUT = 60


def _tasks_dir() -> Path:
    if CONTAINER_TASKS.exists():
        return CONTAINER_TASKS
    return TASKS_DIR


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


def execute(task_name: str, args: dict | str | None = None, timeout: int = TIMEOUT) -> dict:
    """Execute task — WORKFLOW.md:77
    args: dict -> JSON string passed as $1 and stdin
    Returns {status: ok|error, output, error, exit_code, task}
    """
    task_name = task_name.strip()
    run_path, kind = _resolve_task(task_name)

    # normalize args to string
    if args is None:
        args_str = ""
    elif isinstance(args, dict):
        args_str = json.dumps(args, ensure_ascii=False)
    else:
        args_str = str(args)

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
        status = "ok" if proc.returncode == 0 else "error"
        return {
            "status": status,
            "output": proc.stdout.strip(),
            "error": proc.stderr.strip() if proc.returncode != 0 else "",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "task": task_name,
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
        }
    except Exception as e:
        return {
            "status": "error",
            "output": "",
            "error": str(e),
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1,
            "task": task_name,
        }
