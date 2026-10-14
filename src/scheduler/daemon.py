"""Cron daemon — WORKFLOW.md Phase 9

Long-running loop that fires due cron jobs using real croniter due-detection
(replacing the old fixed 60s tick in src/main.py). Also runs the temp-instance
reaper once a day. Started from docker-entrypoint.sh alongside the GUI.
"""
import time
from datetime import datetime, timedelta, timezone

from src.action import logbook
from src.scheduler import registry
from src.scheduler.jobs import execute_job

TICK_SECONDS = 30
REAP_EVERY_SECONDS = 24 * 3600
# How recently a scheduled fire time must be to count as "due this tick".
# Cron granularity is 1 minute, so this must exceed 60s to survive tick jitter.
DUE_WINDOW_SECONDS = 90

_lock_state = {"started_at": None, "last_tick": None, "ticks": 0, "fired": 0, "reaped_at": None}


def _log(msg: str) -> None:
    print(f"[scheduler] {msg}", flush=True)


def _now():
    return datetime.now(timezone.utc)


def _parse_iso(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _is_due(job: dict, now, window_seconds: int = DUE_WINDOW_SECONDS) -> bool:
    """True if a cron job should fire now.

    Uses croniter: the job is due when the schedule's most recent fire time
    falls inside the current tick window AND we have not already run it since.
    The window matters — without it a job like "0 5 1 1 *" (5am on New Year's
    Day) would look "due" forever and fire on every daemon start.

    Tracking last_run_at in jobs.json means a container restart inside the same
    window will not double-fire.
    """
    from croniter import croniter

    sched = job.get("schedule", "")
    if not sched:
        return False
    try:
        itr = croniter(sched, now)
        prev = itr.get_prev(datetime)
    except Exception:
        return False
    # only fire if that fire time is recent enough to still be "this tick"
    if prev > now:
        return False
    if (now - prev).total_seconds() > window_seconds:
        return False
    last = _parse_iso(job.get("last_run_at"))
    return last is None or last < prev


def _maybe_reap(now) -> None:
    last = _parse_iso(_lock_state.get("reaped_at"))
    if last and (now - last).total_seconds() < REAP_EVERY_SECONDS:
        return
    try:
        from src.action.instances import reap_temp
        removed = reap_temp()
        _lock_state["reaped_at"] = now.isoformat()
        _log(f"reaped {len(removed)} temp instance(s)")
    except Exception as e:
        _log(f"reaper error: {e}")


def tick(mock: bool = False) -> list[dict]:
    """One scheduler tick. Fires every due cron job. Returns fired results."""
    now = _now()
    fired = []
    for job in registry.enabled_jobs(kind="cron"):
        if not _is_due(job, now):
            continue
        jid = job.get("id")
        _log(f"firing {jid} ({job['task']}) on '{job['schedule']}'")
        # mark BEFORE running so a slow job isn't re-fired on the next tick
        try:
            registry.mark_run(jid, when=now.isoformat())
        except Exception:
            pass
        try:
            res = execute_job(job, mock=mock)
        except Exception as e:
            _log(f"{jid}: ERROR {e}")
            res = {"status": "error", "error": str(e)}
        fired.append({"id": jid, "status": res.get("status")})
        _lock_state["fired"] += 1
    return fired


def run_forever(tick_seconds: int = TICK_SECONDS, once: bool = False, mock: bool = False) -> None:
    """Main scheduler loop. once=True runs a single tick and returns."""
    _lock_state["started_at"] = _now().isoformat()
    _log(f"daemon started (tick {tick_seconds}s)")
    while True:
        try:
            fired = tick(mock=mock)
            if fired:
                _log(f"fired {len(fired)} job(s)")
        except Exception as e:
            _log(f"tick error: {e}")
        now = _now()
        _lock_state["last_tick"] = now.isoformat()
        _lock_state["ticks"] += 1
        try:
            _maybe_reap(now)
        except Exception:
            pass
        if once:
            return
        time.sleep(tick_seconds)


def status() -> dict:
    """Scheduler health for the GUI."""
    return {
        "running": _lock_state["started_at"] is not None,
        "started_at": _lock_state["started_at"],
        "last_tick": _lock_state["last_tick"],
        "ticks": _lock_state["ticks"],
        "fired": _lock_state["fired"],
        "tick_seconds": TICK_SECONDS,
    }


if __name__ == "__main__":
    import argparse
    import json

    p = argparse.ArgumentParser(description="Banana cron daemon")
    p.add_argument("--once", action="store_true", help="single tick then exit")
    p.add_argument("--tick", type=int, default=TICK_SECONDS)
    p.add_argument("--status", action="store_true")
    a = p.parse_args()

    if a.status:
        print(json.dumps(status(), indent=2, ensure_ascii=False))
    else:
        run_forever(tick_seconds=a.tick, once=a.once)