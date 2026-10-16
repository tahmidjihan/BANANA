"""instance_id tests — Phase 8 deferred item

A job or a plan step may pin its result into instances/permanent/<id> so it
survives the 72h temp reaper.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.action import instances as inst_mod
from src.action.runner import run_steps
from src.scheduler import registry
from src.scheduler.jobs import execute_job
from src.scheduler.registry import create, normalize

from tests.test_failures import isolated_log  # noqa: F401  (reused fixture)


@pytest.fixture(autouse=True)
def isolated_perm(tmp_path, monkeypatch):
    """Point the instance dirs at tmp so the real instances/ is untouched"""
    temp = tmp_path / "temp"
    perm = tmp_path / "permanent"
    temp.mkdir()
    perm.mkdir()
    monkeypatch.setattr(inst_mod, "_temp_dir", lambda: temp)
    monkeypatch.setattr(inst_mod, "_perm_dir", lambda: perm)
    return perm


@pytest.fixture(autouse=True)
def isolated_jobs(tmp_path, monkeypatch):
    p = tmp_path / "jobs.json"
    monkeypatch.setattr(registry, "jobs_path", lambda: p)
    return p


# --- registry validation ---

def test_normalize_keeps_instance_id():
    j = normalize({"kind": "boot", "task": "echo-demo", "instance_id": "keepme"})
    assert j["instance_id"] == "keepme"


def test_normalize_omits_instance_id_by_default():
    assert "instance_id" not in normalize({"kind": "boot", "task": "echo-demo"})


@pytest.mark.parametrize("bad", ["../escape", "a/b", ".hidden"])
def test_normalize_rejects_bad_instance_id(bad):
    with pytest.raises(ValueError, match="invalid instance_id"):
        normalize({"kind": "boot", "task": "echo-demo", "instance_id": bad})


def test_create_job_with_instance_id():
    j = create({"id": "p1", "kind": "boot", "task": "echo-demo", "instance_id": "keeper"})
    assert j["instance_id"] == "keeper"


# --- job execution ---

def test_job_writes_to_permanent_instance(isolated_perm):
    create({"id": "p2", "kind": "boot", "task": "echo-demo",
            "args": {"msg": "persist me"}, "instance_id": "keeper"})
    res = execute_job(registry.get("p2"))
    assert res["status"] == "ok"
    assert res["instance_kind"] == "permanent"
    d = isolated_perm / "keeper"
    assert d.exists()
    ctx = json.loads((d / "context.json").read_text())
    assert ctx["result"]["output"] == "echo-demo: persist me"


def test_job_without_instance_id_uses_temp():
    create({"id": "p3", "kind": "boot", "task": "echo-demo"})
    res = execute_job(registry.get("p3"))
    assert res["instance_kind"] == "temp"


def test_job_reuses_same_permanent_dir_across_runs(isolated_perm):
    create({"id": "p4", "kind": "boot", "task": "echo-demo",
            "args": {"msg": "second"}, "instance_id": "keeper"})
    execute_job(registry.get("p4"))
    execute_job(registry.get("p4"))
    assert list(isolated_perm.iterdir()) == [isolated_perm / "keeper"], "one dir, overwritten"


# --- plan steps ---

def test_step_with_instance_id_pins_result(isolated_perm):
    out = run_steps([
        {"task": "echo-demo", "args": {"msg": "pinned"}, "instance_id": "step-pin"},
    ])
    assert out["status"] == "ok"
    d = isolated_perm / "step-pin"
    assert d.exists()
    ctx = json.loads((d / "context.json").read_text())
    assert ctx["result"]["output"] == "echo-demo: pinned"
    assert ctx["given"]["meta"]["step"] == 1
    assert ctx["given"]["meta"]["instance_id"] == "step-pin"


def test_step_trace_lands_in_permanent_dir(isolated_perm):
    out = run_steps([
        {"task": "echo-demo", "args": {"msg": "traced"}, "instance_id": "step-trace"},
    ])
    trace = isolated_perm / "step-trace" / "steps" / "1.json"
    assert trace.exists()
    assert json.loads(trace.read_text())["task"] == "echo-demo"


def test_step_without_instance_id_creates_nothing_permanent(isolated_perm):
    run_steps([{"task": "echo-demo", "args": {"msg": "temp only"}}])
    assert list(isolated_perm.iterdir()) == []


def test_bad_instance_id_does_not_fail_the_step(isolated_perm):
    """A bad id must not sink the run — the task output is still returned."""
    out = run_steps([
        {"task": "echo-demo", "args": {"msg": "kept"}, "instance_id": "../escape"},
    ])
    assert out["status"] == "ok"
    assert out["steps"][0]["output"] == "echo-demo: kept"
    assert "instance_error" in out["steps"][0]
    assert not (isolated_perm.parent / "escape").exists()