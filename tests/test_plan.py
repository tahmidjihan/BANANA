"""Phase 8 multi-step job tests — run inside Docker
docker compose run --rm banana python -m pytest tests/ -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.action import logbook
from src.action.plan import (
    MAX_CHAINED_CHARS,
    MAX_STEPS,
    bind_args,
    parse_plan,
    validate,
)
from src.action.runner import run_job, run_steps, write_job_trace

from tests.test_failures import isolated_log  # noqa: F401  (reused fixture)


def always(x):
    return True


# --- parsing: line format ---

def test_parses_two_step_plan():
    text = """Here is the plan:
PLAN:
- step 1: echo-demo {"msg": "hello"}
- step 2: reverse-text {"msg": "seed"} uses: $prev
Done."""
    steps = parse_plan(text)
    assert len(steps) == 2
    assert steps[0]["task"] == "echo-demo"
    assert steps[0]["args"] == {"msg": "hello"}
    assert steps[1]["task"] == "reverse-text"
    assert steps[1]["uses"] == "$prev"


def test_parses_steps_without_numbers():
    steps = parse_plan('PLAN:\n- echo-demo {"msg":"a"}\n- count-words')
    assert [s["task"] for s in steps] == ["echo-demo", "count-words"]


def test_parses_nested_json_args():
    steps = parse_plan('PLAN:\n- echo-demo {"msg": "x", "opts": {"deep": [1,2]}}')
    assert steps[0]["args"]["opts"] == {"deep": [1, 2]}


def test_no_plan_returns_empty():
    assert parse_plan("TASK: echo-demo\nARGS: {\"msg\":\"hi\"}") == []
    assert parse_plan("") == []
    assert parse_plan("just prose about echo-demo") == []


def test_plan_takes_precedence_over_task_line():
    """A PLAN block wins even if the prose mentions TASK:"""
    text = "PLAN:\n- step 1: echo-demo {\"msg\":\"a\"}\n- step 2: count-words uses: step1\nTASK: echo-demo"
    steps = parse_plan(text)
    assert len(steps) == 2


def test_stops_at_first_non_step_line():
    text = "PLAN:\n- step 1: echo-demo {\"msg\":\"a\"}\nThat is all.\n- step 2: count-words"
    assert len(parse_plan(text)) == 1


# --- parsing: JSON format ---

def test_parses_json_plan_object():
    text = '```json\n{"plan":[{"task":"echo-demo","args":{"msg":"a"}},{"task":"count-words"}]}\n```'
    steps = parse_plan(text)
    assert [s["task"] for s in steps] == ["echo-demo", "count-words"]
    assert steps[0]["args"] == {"msg": "a"}


def test_parses_json_steps_key():
    text = '{"steps":[{"task":"echo-demo","args":{"msg":"a"}}]}'
    assert len(parse_plan(text)) == 1


# --- validation ---

def test_validate_ok():
    out = validate([{"task": "echo-demo", "args": {}, "uses": None}], always)
    assert out["ok"]


def test_validate_rejects_unknown_task_before_running():
    out = validate([{"task": "echo-demo", "args": {}, "uses": None},
                    {"task": "nope", "args": {}, "uses": None}], lambda t: t != "nope")
    assert not out["ok"]
    assert out["error_kind"] == "not_found"
    assert "nope" in out["error"]


def test_validate_rejects_too_many_steps():
    steps = [{"task": "echo-demo", "args": {}, "uses": None} for _ in range(MAX_STEPS + 1)]
    out = validate(steps, always)
    assert not out["ok"]
    assert out["error_kind"] == "too_many_steps"


def test_validate_rejects_unresolvable_ref():
    out = validate([{"task": "echo-demo", "args": {}, "uses": "step99"}], always)
    assert not out["ok"]
    assert out["error_kind"] == "parse_error"


def test_validate_rejects_empty():
    out = validate([], always)
    assert not out["ok"]
    assert out["error_kind"] == "parse_error"


# --- chaining ---

def test_bind_args_fills_msg_when_no_args():
    steps = [{"task": "x", "args": {"msg": "seed"}, "uses": None},
             {"task": "reverse-text", "args": {}, "uses": "$prev"}]
    bind_args(steps, {1: "hello"})
    assert steps[1]["args"]["msg"] == "hello"
    assert steps[1]["args"]["_prev_output"] == "hello"


def test_bind_args_does_not_clobber_explicit_args():
    steps = [{"task": "x", "args": {"msg": "seed"}, "uses": None},
             {"task": "reverse-text", "args": {"msg": "mine"}, "uses": "$prev"}]
    bind_args(steps, {1: "hello"})
    assert steps[1]["args"]["msg"] == "mine"
    assert steps[1]["args"]["_prev_output"] == "hello"


def test_bind_args_ignores_prev_on_first_step():
    """step 1 has no previous step — the ref cannot resolve, leave args alone"""
    steps = [{"task": "reverse-text", "args": {}, "uses": "$prev"}]
    bind_args(steps, {1: "hello"})
    assert "_prev_output" not in steps[0]["args"]


def test_bind_args_truncates():
    steps = [{"task": "x", "args": {"msg": "seed"}, "uses": None},
             {"task": "reverse-text", "args": {}, "uses": "$prev"}]
    bind_args(steps, {1: "x" * 9000})
    assert len(steps[1]["args"]["_prev_output"]) == MAX_CHAINED_CHARS


def test_bind_args_can_reference_earlier_step():
    steps = [
        {"task": "echo-demo", "args": {"msg": "a"}, "uses": None},
        {"task": "count-words", "args": {}, "uses": None},
        {"task": "reverse-text", "args": {}, "uses": "step1"},
    ]
    bind_args(steps, {1: "FIRST", 2: "SECOND"})
    assert steps[2]["args"]["_prev_output"] == "FIRST"


# --- execution ---

def test_run_steps_chains_real_output():
    """echo-demo prefixes its output, so step 2 counts words in that prefix too"""
    out = run_steps([
        {"task": "echo-demo", "args": {"msg": "hello world"}},
        {"task": "count-words", "args": {}, "uses": "$prev"},
    ])
    assert out["status"] == "ok"
    assert "echo-demo: hello world" in out["steps"][0]["output"]
    assert out["steps"][1]["output"] == "3", "step 2 counted words from step 1's output"


def test_run_job_validates_whole_plan_first():
    """A bad task in step 2 means step 1 never runs."""
    out = run_job(
        'PLAN:\n- step 1: echo-demo {"msg":"a"}\n- step 2: definitely-not-a-task',
        validate_task=lambda t: t != "definitely-not-a-task",
    )
    assert out["status"] == "error"
    assert out["error_kind"] == "not_found"
    assert out["steps"] == [], "nothing executed"
    assert logbook.read(limit=1)[0]["error_kind"] == "not_found", "failure logged"


def test_run_job_without_plan_is_parse_error():
    out = run_job("TASK: echo-demo\nARGS: {}", validate_task=always)
    assert out["error_kind"] == "parse_error"


def test_run_job_end_to_end_two_steps():
    out = run_job(
        'PLAN:\n- step 1: echo-demo {"msg": "hello world"}\n- step 2: reverse-text uses: $prev'
    )
    assert out["status"] == "ok"
    assert len(out["steps"]) == 2
    assert out["steps"][0]["output"].endswith("hello world")
    assert out["steps"][1]["output"] == "dlrow olleh :omed-ohce", "reversed step 1 output"


def test_run_job_writes_step_trace(tmp_path):
    out = run_job('PLAN:\n- step 1: echo-demo {"msg":"a"}\n- step 2: count-words uses: $prev')
    inst = tmp_path / "inst"
    inst.mkdir()
    write_job_trace(inst, out["steps"])
    assert (inst / "steps" / "1.json").exists()
    assert (inst / "steps" / "2.json").exists()
    import json
    s1 = json.loads((inst / "steps" / "1.json").read_text())
    assert s1["task"] == "echo-demo"
    assert s1["status"] == "ok"
    assert s1["output"].endswith("a")


def test_run_job_fail_fast_on_step_failure():
    out = run_job(
        'PLAN:\n- step 1: fail-demo {"code": 1}\n- step 2: echo-demo {"msg":"never"}',
        policy="fail_fast",
    )
    assert out["status"] == "error"
    assert out["failed_at"] == 1
    assert len(out["steps"]) == 1


def test_run_job_continue_past_failure():
    out = run_job(
        'PLAN:\n- step 1: fail-demo {"code": 1}\n- step 2: echo-demo {"msg":"still runs"}',
        policy="continue",
    )
    assert out["failed_at"] == 1
    assert len(out["steps"]) == 2
    assert out["steps"][1]["status"] == "ok"


def test_every_step_is_logged_under_one_job_id():
    job_id = "job-abc"
    run_job(
        'PLAN:\n- step 1: echo-demo {"msg":"a"}\n- step 2: count-words uses: $prev',
        job_id=job_id,
    )
    entries = logbook.read(limit=50, job_id=job_id)
    assert len(entries) == 2
    assert {e["task"] for e in entries} == {"echo-demo", "count-words"}