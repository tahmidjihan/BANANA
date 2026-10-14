"""Boot jobs — WORKFLOW.md Phase 9

Runs every enabled `kind=boot` job once when the container starts, in registry
order, honouring each job's delay_seconds to stagger them. Records
boot_completed_at so a restart is visible in the UI.
"""
import sys
import time
from datetime import datetime, timezone

from src.scheduler import registry
from src.scheduler.jobs import execute_job


def _log(msg: str) -> None:
    print(f"[boot] {msg}", flush=True)


def run_boot_jobs(skip: bool = False, mock: bool = False) -> dict:
    """Run all enabled boot jobs sequentially. Returns a summary dict.
    skip=True returns immediately (--skip-boot-jobs, for fast restarts/tests).
    """
    if skip:
        _log("skipped (--skip-boot-jobs)")
        return {"skipped": True, "ran": 0, "results": []}

    jobs = registry.enabled_jobs(kind="boot")
    if not jobs:
        _log("no boot jobs configured")
        return {"skipped": False, "ran": 0, "results": []}

    _log(f"running {len(jobs)} boot job(s)")
    results = []
    for job in jobs:
        delay = int(job.get("delay_seconds") or 0)
        if delay:
            _log(f"{job['id']}: waiting {delay}s")
            time.sleep(delay)
        _log(f"{job['id']}: running {job['task']}")
        try:
            res = execute_job(job, mock=mock)
        except Exception as e:  # a bad job must not stop the rest
            _log(f"{job['id']}: ERROR {e}")
            results.append({"id": job["id"], "status": "error", "error": str(e)})
            continue
        # mark_run with boot=True so the UI shows boot_completed_at
        try:
            registry.mark_run(job["id"], when=datetime.now(timezone.utc).isoformat(), boot=True)
        except Exception:
            pass
        results.append({
            "id": job["id"],
            "status": res.get("status"),
            "error_kind": res.get("error_kind"),
            "output": (res.get("output") or "")[:200],
        })
        _log(f"{job['id']}: {res.get('status')}")

    ok = sum(1 for r in results if r.get("status") == "ok")
    _log(f"done — {ok}/{len(results)} ok")
    return {"skipped": False, "ran": len(results), "results": results}


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Run Banana boot jobs")
    p.add_argument("--skip", action="store_true", help="do not run, just report")
    p.add_argument("--dry-run", action="store_true", help="list boot jobs and exit")
    a = p.parse_args()

    if a.dry_run:
        import json
        print(json.dumps(registry.by_kind("boot"), indent=2, ensure_ascii=False))
    else:
        import json
        summary = run_boot_jobs(skip=a.skip)
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))