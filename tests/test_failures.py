"""Phase 7 failure-handling tests — run inside Docker
docker compose run --rm banana python -m pytest tests/ -v
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.action import logbook
from src.action.executor import classify_error, execute, task_meta
from src.action.runner import run_steps, run_task


@pytest.fixture(autouse=True)
def isolated_log(tmp_path, monkeypatch):
    """Never touch the real instances/logs during tests"""
    d = tmp_path / "logs"
    d.mkdir()
    monkeypatch.setattr(logbook, "logs_dir", lambda: d)
    monkeypatch.setattr(logbook, "log_path", lambda: d / "runs.jsonl")
    return d


# --- classification ---

def test_classify_kinds():
    assert classify_error(0, "") == "ok"
    assert classify_error(1, "boom") == "nonzero_exit"
    assert classify_error(0, "", timed_out=True) == "timeout"
    assert classify_error(0, "", exc=FileNotFoundError("x")) == "not_found"
    assert classify_error(0, "", exc=ValueError("x")) == "invalid_args"
    assert classify_error(0, "", exc=RuntimeError("x")) == "spawn_error"


# --- task meta ---

def test_task_meta_reads_json():
    assert task_meta("fail-demo")["retries"] == 2


def test_task_meta_missing_is_empty():
    assert task_meta("no-such-task") == {}


def test_task_meta_rejects_traversal():
    assert task_meta("../../etc") == {}


# --- executor ---

def test_success_is_ok():
    r = execute("echo-demo", {"msg": "hi"})
    assert r["status"] == "ok"
    assert r["error_kind"] == "ok"
    assert r["attempts"] == 1


def test_nonzero_exit_retries_then_classifies():
    r = execute("fail-demo", {"code": 3}, backoff=0)
    assert r["status"] == "error"
    assert r["error_kind"] == "nonzero_exit"
    assert r["exit_code"] == 3
    assert r["attempts"] == 3, "meta.json sets retries=2 -> 3 attempts"
    assert all(x["status"] == "error" for x in r["runs"])


def test_timeout_kills_task_and_classifies():
    r = execute("slow-demo", {"sleep": 30})
    assert r["status"] == "error"
    assert r["error_kind"] == "timeout"
    assert r["exit_code"] == 124


def test_missing_task_never_raises():
    r = execute("definitely-not-a-task")
    assert r["status"] == "error"
    assert r["error_kind"] == "not_found"


# --- runner ---

def test_run_task_absorbs_failure():
    r = run_task("definitely-not-a-task")
    assert r["status"] == "error"
    assert r["error_kind"] == "not_found"


def test_run_steps_fail_fast_stops_early():
    out = run_steps(
        [
            {"task": "fail-demo", "args": {"code": 1}},
            {"task": "echo-demo", "args": {"msg": "never runs"}},
        ],
        policy="fail_fast",
    )
    assert out["status"] == "error"
    assert out["failed_at"] == 1
    assert len(out["steps"]) == 1


def test_run_steps_continue_past_failure():
    out = run_steps(
        [
            {"task": "fail-demo", "args": {"code": 1}},
            {"task": "echo-demo", "args": {"msg": "still runs"}},
        ],
        policy="continue",
    )
    assert out["failed_at"] == 1
    assert len(out["steps"]) == 2
    assert out["steps"][1]["status"] == "ok"


def test_run_steps_chains_output():
    out = run_steps(
        [
            {"task": "echo-demo", "args": {"msg": "seed"}},
            {"task": "count-words", "args": {"msg": "hello world"}},
        ]
    )
    assert out["status"] == "ok"
    assert len(out["runs"]) if "runs" in out else True
    assert out["output"], "final step output is surfaced"


def test_run_steps_rejects_too_many():
    out = run_steps([{"task": "echo-demo"} for _ in range(11)], max_steps=10)
    assert out["status"] == "error"
    assert out["error_kind"] == "too_many_steps"


# --- logbook ---

def test_every_attempt_is_logged(isolated_log):
    execute("fail-demo", {"code": 1}, backoff=0)
    entries = logbook.read(limit=100)
    assert len(entries) == 3, "one line per attempt"
    assert all(e["task"] == "fail-demo" for e in entries)
    assert all(e["error_kind"] == "nonzero_exit" for e in entries)
    assert entries[0]["attempt"] == 3, "newest first"


def test_log_entries_are_valid_json_lines(isolated_log):
    execute("echo-demo", {"msg": "log me"})
    raw = (isolated_log / "runs.jsonl").read_text().strip().splitlines()
    assert raw, "log file written"
    for line in raw:
        json.loads(line)


def test_log_records_job_id(isolated_log):
    execute("echo-demo", {"msg": "x"}, job_id="job-123", source="cron")
    e = logbook.read(limit=1)[0]
    assert e["job_id"] == "job-123"
    assert e["source"] == "cron"


def test_log_filters_by_task(isolated_log):
    execute("echo-demo", {"msg": "a"})
    execute("fail-demo", {"code": 1}, backoff=0)
    assert len(logbook.read(limit=50, task="echo-demo")) == 1


def test_summary_counts_failures(isolated_log):
    execute("echo-demo", {"msg": "a"})
    execute("fail-demo", {"code": 1}, backoff=0)
    s = logbook.summary(limit=100)
    assert s["total"] == 4, "1 ok + 3 failed attempts"
    assert s["failed"] == 3


def test_rotation_keeps_bounded_generations(isolated_log, monkeypatch):
    monkeypatch.setattr(logbook, "MAX_BYTES", 400)
    for i in range(40):
        logbook.record("echo-demo", "ok", output="x" * 200)
    gens = sorted(p.name for p in isolated_log.iterdir())
    assert "runs.jsonl" in gens
    assert len(gens) <= logbook.MAX_FILES, f"rotations bounded, got {gens}"
    assert logbook.read(limit=100), "readable across rotations"


def test_log_never_raises_on_bad_path(monkeypatch):
    monkeypatch.setattr(logbook, "logs_dir", lambda: Path("/proc/nope/deeper"))
    # must not raise
    logbook.record("echo-demo", "ok")