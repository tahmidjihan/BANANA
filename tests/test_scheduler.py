"""Phase 9 scheduler tests — run inside Docker
docker compose run --rm banana python -m pytest tests/ -q
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.action import logbook
from src.detector.detector import from_message
from src.scheduler import boot, daemon, registry
from src.scheduler.jobs import execute_job, preview
from src.scheduler.registry import create, delete, get, grouped, normalize, toggle, update

from tests.test_failures import isolated_log  # noqa: F401  (reused fixture)


@pytest.fixture(autouse=True)
def isolated_jobs(tmp_path, monkeypatch):
    """Never touch the real config/jobs.json during tests"""
    p = tmp_path / "jobs.json"
    monkeypatch.setattr(registry, "jobs_path", lambda: p)
    return p


# --- registry CRUD ---

def test_create_cron_job():
    j = create({"id": "j1", "kind": "cron", "schedule": "0 5 * * *", "task": "echo-demo"})
    assert j["id"] == "j1"
    assert j["enabled"] is True
    assert j["schedule"] == "0 5 * * *"
    assert get("j1")["task"] == "echo-demo"


def test_create_boot_job():
    j = create({"id": "b1", "kind": "boot", "task": "echo-demo", "delay_seconds": 5})
    assert j["kind"] == "boot"
    assert j["delay_seconds"] == 5


def test_create_generates_id_when_missing():
    j = create({"kind": "boot", "task": "echo-demo"})
    assert j["id"].startswith("boot-")


def test_create_rejects_bad_cron():
    with pytest.raises(ValueError, match="invalid cron"):
        create({"kind": "cron", "schedule": "not a cron", "task": "echo-demo"})


def test_create_requires_task():
    with pytest.raises(ValueError, match="task is required"):
        create({"kind": "cron", "schedule": "* * * * *"})


def test_create_rejects_bad_kind():
    with pytest.raises(ValueError, match="kind must be"):
        create({"kind": "whenever", "schedule": "* * * * *", "task": "echo-demo"})


def test_create_rejects_path_traversal_task():
    with pytest.raises(ValueError, match="invalid task"):
        create({"kind": "boot", "task": "../../etc/passwd"})


def test_create_rejects_duplicate_id():
    create({"id": "dup", "kind": "boot", "task": "echo-demo"})
    with pytest.raises(ValueError, match="already exists"):
        create({"id": "dup", "kind": "boot", "task": "echo-demo"})


def test_delete():
    create({"id": "d1", "kind": "boot", "task": "echo-demo"})
    assert delete("d1") is True
    assert delete("d1") is False
    assert get("d1") is None


def test_update_keeps_created_at_and_id():
    create({"id": "u1", "kind": "cron", "schedule": "* * * * *", "task": "echo-demo"})
    before = get("u1")["created_at"]
    after = update("u1", {"task": "count-words"})
    assert after["task"] == "count-words"
    assert after["id"] == "u1"
    assert after["created_at"] == before


def test_update_returns_none_for_missing():
    assert update("nope", {"task": "x"}) is None


def test_toggle_flips_enabled():
    create({"id": "t1", "kind": "boot", "task": "echo-demo", "enabled": True})
    assert toggle("t1")["enabled"] is False
    assert toggle("t1")["enabled"] is True
    assert toggle("t1", True)["enabled"] is True


def test_enabled_jobs_filters_kind_and_enabled():
    create({"id": "c1", "kind": "cron", "schedule": "* * * * *", "task": "echo-demo"})
    create({"id": "c2", "kind": "cron", "schedule": "* * * * *", "task": "echo-demo", "enabled": False})
    create({"id": "b1", "kind": "boot", "task": "echo-demo"})
    assert {j["id"] for j in registry.enabled_jobs(kind="cron")} == {"c1"}
    assert {j["id"] for j in registry.enabled_jobs(kind="boot")} == {"b1"}


def test_grouped_buckets_by_kind():
    create({"id": "c1", "kind": "cron", "schedule": "* * * * *", "task": "echo-demo"})
    create({"id": "b1", "kind": "boot", "task": "echo-demo"})
    g = grouped()
    assert [j["id"] for j in g["cron"]] == ["c1"]
    assert [j["id"] for j in g["boot"]] == ["b1"]
    assert g["webhook"] == []


def test_mark_run_sets_timestamps():
    create({"id": "m1", "kind": "boot", "task": "echo-demo"})
    registry.mark_run("m1", boot=True)
    j = get("m1")
    assert j["last_run_at"]
    assert j["boot_completed_at"]


def test_mark_run_clears_boot_flag_for_cron():
    create({"id": "m2", "kind": "cron", "schedule": "* * * * *", "task": "echo-demo"})
    registry.mark_run("m2", boot=True)
    assert get("m2")["boot_completed_at"] == get("m2")["last_run_at"]


def test_corrupt_file_loads_empty_not_crash(isolated_jobs):
    isolated_jobs.write_text("{not json")
    assert registry.load()["jobs"] == []


def test_missing_file_loads_empty():
    assert registry.load()["jobs"] == []


def test_save_survives_bind_mount(tmp_path, monkeypatch):
    """tmp+rename fails on a bind-mounted single file — must fall back"""
    p = tmp_path / "jobs.json"
    p.write_text("{}")

    real_replace = Path.replace

    def boom(self, target):
        if str(target) == str(p):
            raise OSError(16, "Device or resource busy")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", boom)
    registry.jobs_path = lambda: p
    registry.save({"version": 1, "jobs": []})
    assert json.loads(p.read_text())["jobs"] == []
    assert not list(tmp_path.glob("*.tmp")), "tmp file cleaned up"


# --- job execution ---

def test_execute_job_runs_task_and_logs():
    create({"id": "e1", "kind": "boot", "task": "echo-demo", "args": {"msg": "job ran"}})
    res = execute_job(get("e1"))
    assert res["status"] == "ok"
    assert res["output"] == "echo-demo: job ran"
    assert res["job_id"] == "e1"
    entries = logbook.read(limit=10, job_id=res["job_run_id"])
    assert len(entries) == 1
    assert entries[0]["task"] == "echo-demo"


def test_execute_job_failure_is_classified():
    create({"id": "e2", "kind": "boot", "task": "fail-demo", "args": {"code": 4}})
    res = execute_job(get("e2"))
    assert res["status"] == "error"
    assert res["error_kind"] == "nonzero_exit"


def test_execute_boot_job_builds_boot_given():
    create({"id": "e3", "kind": "boot", "task": "echo-demo"})
    res = execute_job(get("e3"))
    assert res["given"]["source"] == "boot"


def test_execute_cron_job_builds_cron_given():
    create({"id": "e4", "kind": "cron", "schedule": "0 5 * * *", "task": "echo-demo"})
    res = execute_job(get("e4"))
    assert res["given"]["source"] == "cron"
    assert res["given"]["meta"]["cron_expr"] == "0 5 * * *"


def test_execute_job_without_task_errors():
    res = execute_job({"id": "bad", "kind": "boot", "task": ""})
    assert res["status"] == "error"
    assert res["error_kind"] == "invalid_args"


def test_preview_next_run_for_cron():
    create({"id": "p1", "kind": "cron", "schedule": "0 5 * * *", "task": "echo-demo"})
    assert preview(get("p1")).get("next_run")


def test_preview_empty_for_boot():
    create({"id": "p2", "kind": "boot", "task": "echo-demo"})
    assert preview(get("p2")) == {}


# --- boot jobs ---

def test_boot_runs_enabled_boot_jobs():
    create({"id": "b1", "kind": "boot", "task": "echo-demo", "args": {"msg": "boot"}})
    out = boot.run_boot_jobs()
    assert out["ran"] == 1
    assert out["results"][0]["status"] == "ok"
    assert get("b1")["boot_completed_at"], "boot completion recorded"


def test_boot_skips_disabled_jobs():
    create({"id": "b2", "kind": "boot", "task": "echo-demo", "enabled": False})
    assert boot.run_boot_jobs()["ran"] == 0


def test_boot_skip_flag_runs_nothing():
    create({"id": "b3", "kind": "boot", "task": "echo-demo"})
    out = boot.run_boot_jobs(skip=True)
    assert out["skipped"] is True
    assert out["ran"] == 0
    assert get("b3")["boot_completed_at"] is None


def test_boot_does_not_run_cron_jobs():
    create({"id": "b4", "kind": "cron", "schedule": "* * * * *", "task": "echo-demo"})
    assert boot.run_boot_jobs()["ran"] == 0


def test_boot_one_failure_does_not_stop_others():
    create({"id": "f1", "kind": "boot", "task": "fail-demo", "args": {"code": 1}, "retries": 0})
    create({"id": "f2", "kind": "boot", "task": "echo-demo", "args": {"msg": "still runs"}})
    out = boot.run_boot_jobs()
    assert out["ran"] == 2
    assert out["results"][0]["status"] == "error"
    assert out["results"][1]["status"] == "ok"


# --- cron due detection ---

def test_due_when_never_run():
    create({"id": "d1", "kind": "cron", "schedule": "* * * * *", "task": "echo-demo"})
    assert daemon._is_due(get("d1"), datetime.now(timezone.utc)) is True


def test_not_due_twice_in_same_minute():
    create({"id": "d2", "kind": "cron", "schedule": "* * * * *", "task": "echo-demo"})
    now = datetime.now(timezone.utc)
    registry.mark_run("d2", when=now.isoformat())
    assert daemon._is_due(get("d2"), now) is False


def test_due_again_after_last_fire_window():
    """last run was 5 min ago on a per-minute schedule -> due again now"""
    create({"id": "d3", "kind": "cron", "schedule": "* * * * *", "task": "echo-demo"})
    old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    registry.mark_run("d3", when=old)
    assert daemon._is_due(get("d3"), datetime.now(timezone.utc)) is True


def test_not_due_for_future_schedule():
    create({"id": "d4", "kind": "cron", "schedule": "0 5 1 1 *", "task": "echo-demo"})
    assert daemon._is_due(get("d4"), datetime.now(timezone.utc)) is False


def test_not_due_when_fire_time_is_stale():
    """A never-run daily job seen at 15:00 must NOT fire — its last matching
    time (05:00) is outside the window. Without the window check, every daemon
    start would replay missed daily jobs."""
    create({"id": "d5", "kind": "cron", "schedule": "0 5 * * *", "task": "echo-demo"})
    afternoon = datetime.now(timezone.utc).replace(hour=15, minute=0, second=0, microsecond=0)
    assert daemon._is_due(get("d5"), afternoon) is False


def test_due_for_daily_job_inside_window():
    create({"id": "d6", "kind": "cron", "schedule": "0 5 * * *", "task": "echo-demo"})
    just_after = datetime.now(timezone.utc).replace(hour=5, minute=0, second=30, microsecond=0)
    assert daemon._is_due(get("d6"), just_after) is True


def test_tick_fires_due_job_once():
    create({"id": "k1", "kind": "cron", "schedule": "* * * * *", "task": "echo-demo", "args": {"msg": "tick"}})
    assert len(daemon.tick()) == 1
    assert daemon.tick() == [], "second tick in same minute does not refire"


def test_tick_skips_disabled():
    create({"id": "k2", "kind": "cron", "schedule": "* * * * *", "task": "echo-demo", "enabled": False})
    assert daemon.tick() == []


def test_tick_marks_run_before_executing():
    """last_run_at is set even if the task fails, so a slow/failing job
    cannot be re-fired on every tick"""
    create({"id": "k3", "kind": "cron", "schedule": "* * * * *", "task": "fail-demo",
            "args": {"code": 1}, "retries": 0})
    daemon.tick()
    assert get("k3")["last_run_at"] is not None


def test_daemon_once_runs_single_tick():
    create({"id": "k4", "kind": "cron", "schedule": "* * * * *", "task": "echo-demo"})
    daemon.run_forever(once=True)
    st = daemon.status()
    assert st["ticks"] == 1
    assert st["running"] is True


def test_daemon_tolerates_bad_schedule():
    """A job with an unparseable schedule must not kill the loop"""
    create({"id": "k5", "kind": "cron", "schedule": "* * * * *", "task": "echo-demo"})
    bad = {"id": "k6", "kind": "cron", "schedule": "!!!", "task": "echo-demo"}
    assert daemon._is_due(bad, datetime.now(timezone.utc)) is False
    daemon.run_forever(once=True)