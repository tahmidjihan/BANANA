"""Job registry — WORKFLOW.md Phase 9

File-based job store at config/jobs.json. No DB (AGENTS.md:5).
Shared by the CLI, the GUI and the daemon so there is one source of truth.

Job object:
{
  "id": "morning-news",
  "kind": "cron" | "boot" | "webhook",
  "schedule": "0 5 * * *",        # cron only
  "delay_seconds": 0,             # boot only — stagger sequential boot jobs
  "task": "daily-news",           # task to run
  "args": {},                     # task args
  "enabled": true,
  "timeout": 60,
  "retries": 1,
  "last_run_at": null,            # ISO — prevents duplicate runs across restarts
  "boot_completed_at": null,      # ISO — boot jobs only
  "created_at": "...",
  "timezone": null                # cron only — defaults to UTC; "Asia/Dhaka" supported
}
"""
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
CONTAINER_CONFIG = Path("/app/config")

KINDS = ("cron", "boot", "webhook")
MAX_JOBS = 100

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def jobs_path() -> Path:
    base = CONTAINER_CONFIG if CONTAINER_CONFIG.exists() else CONFIG_DIR
    return base / "jobs.json"


def _empty() -> dict:
    return {"version": 1, "jobs": []}


def load() -> dict:
    """Load the registry. A missing or corrupt file yields an empty registry
    rather than crashing the scheduler."""
    p = jobs_path()
    if not p.exists():
        return _empty()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return _empty()
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        return _empty()
    return {"version": data.get("version", 1), "jobs": [j for j in data["jobs"] if isinstance(j, dict)]}


def save(data: dict) -> Path:
    """Write the registry.

    Normally atomic (tmp + rename) so a crash mid-write cannot corrupt the file.
    But config/jobs.json is a bind-mounted *single file* in docker-compose, and
    renaming onto a bind mount fails with EBUSY — so fall back to a direct
    write in that case.
    """
    p = jobs_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    tmp = p.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(p)
        return p
    except OSError:
        # bind-mounted file, or rename blocked — write in place
        try:
            p.write_text(payload, encoding="utf-8")
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
    return p


def valid_cron(expr: str) -> bool:
    if not expr or not str(expr).strip():
        return False
    try:
        from croniter import croniter as _croniter
        _croniter(str(expr).strip(), datetime.now(timezone.utc)).get_next(datetime)
        return True
    except Exception:
        return False


_ID_RE = re.compile(r"^[A-Za-z0-9_\-\.]{1,64}$")


def normalize(job: dict) -> dict:
    """Fill defaults and coerce types. Raises ValueError on an invalid job."""
    if not isinstance(job, dict):
        raise ValueError("job must be an object")

    kind = str(job.get("kind") or "cron").lower().strip()
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")

    task = str(job.get("task") or "").strip()
    if not task:
        raise ValueError("task is required")
    if ".." in task or "/" in task or task.startswith("."):
        raise ValueError(f"invalid task name: {task}")

    out = {
        "id": str(job.get("id") or "").strip(),
        "kind": kind,
        "task": task,
        "args": job.get("args") if isinstance(job.get("args"), dict) else {},
        "enabled": bool(job.get("enabled", True)),
        "timeout": int(job.get("timeout") or 60),
        "retries": int(job.get("retries", 1)),
        "created_at": job.get("created_at") or _now(),
        "last_run_at": job.get("last_run_at"),
        "boot_completed_at": job.get("boot_completed_at"),
    }

    if kind == "cron":
        sched = str(job.get("schedule") or "").strip()
        if not valid_cron(sched):
            raise ValueError(f"invalid cron expression: {sched!r}")
        out["schedule"] = sched
        out["timezone"] = job.get("timezone") or None
    elif kind == "boot":
        out["schedule"] = job.get("schedule") or ""
        out["delay_seconds"] = max(0, int(job.get("delay_seconds") or 0))

    if out["id"] and not _ID_RE.match(out["id"]):
        raise ValueError(f"invalid job id: {out['id']}")
    return out


def create(job: dict) -> dict:
    data = load()
    if len(data["jobs"]) >= MAX_JOBS:
        raise ValueError(f"job limit reached ({MAX_JOBS})")
    new = normalize(job)
    if not new["id"]:
        new["id"] = f"{new['kind']}-{uuid.uuid4().hex[:8]}"
    if any(j.get("id") == new["id"] for j in data["jobs"]):
        raise ValueError(f"job id already exists: {new['id']}")
    data["jobs"].append(new)
    save(data)
    return new


def get(job_id: str) -> dict | None:
    return next((j for j in load()["jobs"] if j.get("id") == job_id), None)


def update(job_id: str, changes: dict) -> dict | None:
    with _lock:
        data = load()
        for i, j in enumerate(data["jobs"]):
            if j.get("id") == job_id:
                merged = {**j, **changes, "id": job_id, "created_at": j.get("created_at") or _now()}
                data["jobs"][i] = normalize(merged)
                save(data)
                return data["jobs"][i]
    return None


def delete(job_id: str) -> bool:
    with _lock:
        data = load()
        before = len(data["jobs"])
        data["jobs"] = [j for j in data["jobs"] if j.get("id") != job_id]
        if len(data["jobs"]) == before:
            return False
        save(data)
        return True


def toggle(job_id: str, enabled: bool | None = None) -> dict | None:
    cur = get(job_id)
    if not cur:
        return None
    return update(job_id, {"enabled": (not cur["enabled"]) if enabled is None else bool(enabled)})


def mark_run(job_id: str, when: str | None = None, boot: bool = False) -> None:
    """Record that a job ran — prevents duplicate runs across restarts."""
    stamp = when or _now()
    with _lock:
        data = load()
        for j in data["jobs"]:
            if j.get("id") == job_id:
                j["last_run_at"] = stamp
                if boot:
                    j["boot_completed_at"] = stamp
                break
        save(data)


def by_kind(kind: str) -> list[dict]:
    return [j for j in load()["jobs"] if j.get("kind") == kind]


def enabled_jobs(kind: str | None = None) -> list[dict]:
    jobs = load()["jobs"]
    if kind:
        jobs = [j for j in jobs if j.get("kind") == kind]
    return [j for j in jobs if j.get("enabled")]


def grouped() -> dict:
    """All jobs bucketed by kind, for the GUI."""
    data = load()
    out = {k: [] for k in KINDS}
    for j in data["jobs"]:
        out.setdefault(j.get("kind", "cron"), []).append(j)
    for v in out.values():
        v.sort(key=lambda j: j.get("id", ""))
    return out


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Banana job registry")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("list").add_argument("--kind", default=None)
    c = sub.add_parser("create")
    c.add_argument("--id", default="")
    c.add_argument("--kind", default="cron", choices=list(KINDS))
    c.add_argument("--schedule", default="")
    c.add_argument("--task", required=True)
    c.add_argument("--args", default="{}")
    c.add_argument("--delay-seconds", type=int, default=0)
    c.add_argument("--disabled", action="store_true")
    d = sub.add_parser("delete")
    d.add_argument("job_id")
    v = sub.add_parser("validate")
    v.add_argument("job_json")

    a = p.parse_args()
    if a.cmd in (None, "list"):
        print(json.dumps(grouped() if not a.kind else by_kind(a.kind), indent=2, ensure_ascii=False))
    elif a.cmd == "create":
        try:
            args = json.loads(a.args) if a.args.strip().startswith("{") else {}
            job = create({
                "id": a.id, "kind": a.kind, "schedule": a.schedule, "task": a.task,
                "args": args, "enabled": not a.disabled, "delay_seconds": a.delay_seconds,
            })
            print(json.dumps(job, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"error: {e}")
            raise SystemExit(1)
    elif a.cmd == "delete":
        print("deleted" if delete(a.job_id) else "not found")
    elif a.cmd == "validate":
        try:
            print(json.dumps(normalize(json.loads(a.job_json)), indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"invalid: {e}")
            raise SystemExit(1)