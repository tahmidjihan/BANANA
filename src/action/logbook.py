"""Run log — WORKFLOW.md Phase 7

Append-only trail of every task attempt to instances/logs/runs.jsonl.
File-based, no DB (AGENTS.md:5). Rotates at MAX_BYTES keeping MAX_FILES generations.
"""
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTANCES = ROOT / "instances"
CONTAINER_INSTANCES = Path("/app/instances")

MAX_BYTES = 5 * 1024 * 1024  # 5MB per generation
MAX_FILES = 3  # keep runs.jsonl + runs.jsonl.1 + runs.jsonl.2

# error kinds — see executor.classify_error
KINDS = (
    "ok",
    "timeout",
    "nonzero_exit",
    "not_found",
    "invalid_args",
    "spawn_error",
)

_lock = threading.Lock()


def logs_dir() -> Path:
    base = CONTAINER_INSTANCES if CONTAINER_INSTANCES.exists() else INSTANCES
    d = base / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_path() -> Path:
    return logs_dir() / "runs.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rotate(path: Path) -> None:
    """runs.jsonl -> .1 -> .2, dropping anything past MAX_FILES"""
    try:
        if not path.exists() or path.stat().st_size < MAX_BYTES:
            return
        oldest = Path(f"{path}.{MAX_FILES - 1}")
        if oldest.exists():
            oldest.unlink()
        for i in range(MAX_FILES - 2, 0, -1):
            src = Path(f"{path}.{i}")
            if src.exists():
                src.replace(Path(f"{path}.{i + 1}"))
        path.replace(Path(f"{path}.1"))
    except OSError:
        # rotation is best-effort — never fail a run because of it
        pass


def _tail(text: str, limit: int = 500) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return "..." + text[-limit:]


def record(
    task: str,
    status: str,
    *,
    job_id: str | None = None,
    source: str | None = None,
    attempt: int = 1,
    attempts: int = 1,
    error: str = "",
    error_kind: str = "",
    exit_code: int | None = None,
    duration_ms: int = 0,
    output: str = "",
    instance: str | None = None,
) -> dict:
    """Append one attempt to the run log. Never raises."""
    entry = {
        "ts": _now(),
        "job_id": job_id or "",
        "task": task,
        "source": source or "",
        "attempt": attempt,
        "attempts": attempts,
        "status": status,
        "error_kind": error_kind or status,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "error": _tail(error, 500),
        "output_tail": _tail(output, 300),
        "instance": instance or "",
    }
    line = json.dumps(entry, ensure_ascii=False)
    with _lock:
        try:
            path = log_path()
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            _rotate(path)
        except Exception:
            pass
    return entry


def read(limit: int = 50, task: str | None = None, job_id: str | None = None) -> list[dict]:
    """Last N entries, newest first. Reads across rotated generations."""
    path = log_path()
    files = [path] + [Path(f"{path}.{i}") for i in range(1, MAX_FILES)]
    lines: list[str] = []
    for f in reversed(files):
        if not f.exists():
            continue
        try:
            lines.extend(f.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
    out = []
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            e = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if task and e.get("task") != task:
            continue
        if job_id and e.get("job_id") != job_id:
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


def summary(limit: int = 200) -> dict:
    """Counts for the GUI — total, failed, by error_kind."""
    entries = read(limit=limit)
    by_kind: dict[str, int] = {}
    failed = 0
    for e in entries:
        kind = e.get("error_kind") or "unknown"
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if e.get("status") != "ok":
            failed += 1
    return {
        "total": len(entries),
        "failed": failed,
        "by_kind": by_kind,
        "last_ts": entries[0].get("ts") if entries else None,
    }


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Banana run log")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--task", default=None)
    p.add_argument("--summary", action="store_true")
    a = p.parse_args()
    if a.summary:
        print(json.dumps(summary(), indent=2))
    else:
        print(json.dumps(read(limit=a.limit, task=a.task), indent=2, ensure_ascii=False))