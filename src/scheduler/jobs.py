"""Job runner — WORKFLOW.md Phase 9

Executes one job from the registry through the normal ACTION layer, so a
scheduled run behaves exactly like a chat-triggered one: retries, error
classification, and a line in runs.jsonl (Phase 7).
"""
import json
from datetime import datetime, timezone

from src.action import logbook
from src.action.runner import run_task
from src.detector.detector import from_cron, from_message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def execute_job(job: dict, mock: bool = False) -> dict:
    """Run a job's task. Never raises — returns a result dict."""
    job_id = job.get("id", "")
    kind = job.get("kind", "cron")
    task = job.get("task", "")
    args = job.get("args") or {}
    job_run_id = f"{job_id}:{_now()}"

    if not task:
        res = {
            "status": "error", "output": "", "error": "job has no task",
            "exit_code": 1, "task": task, "error_kind": "invalid_args",
            "attempts": 0, "runs": [],
        }
        logbook.record(task, "error", job_id=job_run_id, source=kind,
                       attempt=1, attempts=1, error=res["error"],
                       error_kind="invalid_args", exit_code=1)
        return res

    # Build a Given so the run looks identical to a chat-triggered run
    if kind == "cron":
        given = from_cron(job.get("schedule", ""), task_ref=task,
                          meta_extra={"job_id": job_id, "job_run_id": job_run_id})
    elif kind == "boot":
        given = from_message(f"run {task}", source="boot",
                             meta_extra={"job_id": job_id, "job_run_id": job_run_id, "kind": kind})
    else:  # webhook
        given = from_message(f"run {task}", source="webhook",
                             meta_extra={"job_id": job_id, "job_run_id": job_run_id, "kind": kind})

    res = run_task(
        task, args,
        job_id=job_run_id,
        source=kind,
        retries=job.get("retries"),
        timeout=job.get("timeout"),
    )
    res["job_id"] = job_id
    res["job_kind"] = kind
    res["job_run_id"] = job_run_id
    res["given"] = given
    res["started_at"] = _now()

    # Persist an instance per job run so history survives, matching chat runs
    try:
        from src.action.instances import create_temp
        inst = create_temp(given, res)
        res["instance"] = str(inst)
    except Exception:
        pass

    return res


def preview(job: dict) -> dict:
    """Next fire time for a cron job — used by the GUI and the daemon log."""
    if job.get("kind") != "cron":
        return {}
    try:
        from croniter import croniter
        from zoneinfo import ZoneInfo
        base = datetime.now(timezone.utc)
        tzname = job.get("timezone")
        if tzname:
            try:
                base = base.astimezone(ZoneInfo(tzname))
            except Exception:
                pass
        nxt = croniter(job["schedule"], base).get_next(datetime)
        return {"next_run": nxt.isoformat()}
    except Exception as e:
        return {"next_run_error": str(e)}


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Run one Banana job now")
    p.add_argument("job_id")
    p.add_argument("--preview", action="store_true")
    a = p.parse_args()

    from src.scheduler import registry
    job = registry.get(a.job_id)
    if not job:
        print(f"error: no job {a.job_id}")
        raise SystemExit(1)
    if a.preview:
        print(json.dumps(preview(job), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(execute_job(job), indent=2, ensure_ascii=False, default=str))