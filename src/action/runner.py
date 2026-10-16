"""Runner — WORKFLOW.md Phase 7, Phase 8

Wraps execute() so the pipeline never crashes on a task error. Decides what to
do after a give-up: abort the run (fail_fast) or carry on (continue) and report
at the end.

Phase 8 adds multi-step jobs: run_job() parses + validates the WHOLE plan
before step 1 runs, chains step output via `uses`, and persists a per-step
trace under the instance.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from src.action import logbook
from src.action.executor import execute
from src.action.plan import MAX_CHAINED_CHARS, MAX_STEPS, parse_plan, validate

FAIL_FAST = "fail_fast"
CONTINUE = "continue"
DEFAULT_POLICY = FAIL_FAST

JOB_BUDGET_SECONDS = 300


def run_task(
    task: str,
    args: dict | str | None = None,
    *,
    job_id: str | None = None,
    source: str | None = None,
    retries: int | None = None,
    timeout: int | None = None,
) -> dict:
    """Execute one task, absorbing every failure into a result dict.
    Always returns a dict with status/error_kind — never raises.
    """
    try:
        return execute(task, args, timeout=timeout, retries=retries, job_id=job_id, source=source)
    except Exception as e:  # last-resort net so the pipeline survives
        logbook.record(
            task, "error", job_id=job_id, source=source,
            attempt=1, attempts=1, error=str(e), error_kind="spawn_error", exit_code=1,
        )
        return {
            "status": "error",
            "output": "",
            "error": str(e),
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1,
            "task": task,
            "error_kind": "spawn_error",
            "attempts": 0,
            "runs": [],
        }


def _resolve_uses(steps: list[dict], outputs: dict[int, str], i: int) -> None:
    """Bind `uses` refs to prior outputs, in place, right before each step."""
    from src.action.plan import _resolve_ref

    ref = steps[i - 1].get("uses")
    if not ref:
        return
    src = _resolve_ref(ref, i, len(steps))
    if not src:
        return
    val = (outputs.get(src) or "")[:MAX_CHAINED_CHARS]
    args = steps[i - 1].setdefault("args", {})
    if not args:
        args["msg"] = val
    args["_prev_output"] = val


def run_steps(
    steps: list[dict],
    *,
    job_id: str | None = None,
    source: str | None = None,
    policy: str = DEFAULT_POLICY,
    max_steps: int = MAX_STEPS,
    budget_seconds: int = JOB_BUDGET_SECONDS,
    instance_dir: Path | None = None,
) -> dict:
    """Run an ordered list of steps. Phase 8.
    steps: [{"task": name, "args": {...}, "uses": "<prev output>"}]
    Returns {status, steps: [...], failed_at, total_ms, error_kind, output}
    """
    started = time.monotonic()
    results: list[dict] = []
    outputs: dict[int, str] = {}
    status = "ok"
    failed_at = None
    prev_output = ""

    if len(steps) > max_steps:
        return {
            "status": "error",
            "steps": [],
            "failed_at": 0,
            "total_ms": 0,
            "error_kind": "too_many_steps",
            "error": f"{len(steps)} steps exceeds max_steps={max_steps}",
            "output": "",
        }

    for i, step in enumerate(steps, start=1):
        if time.monotonic() - started > budget_seconds:
            status = "error"
            failed_at = i
            results.append({
                "step": i, "task": step.get("task", ""), "status": "error",
                "error_kind": "budget_exceeded", "attempts": 0, "runs": [],
                "error": f"job budget {budget_seconds}s exhausted",
            })
            _write_trace(instance_dir, i, results[-1])
            break

        _resolve_uses(steps, outputs, i)

        res = run_task(step.get("task", ""), step.get("args") or {}, job_id=job_id, source=source)
        res["step"] = i

        # A step may pin its result to a permanent instance so state survives
        # the 72h temp reaper — useful for accumulating output across runs.
        inst_id = str(step.get("instance_id") or "").strip()
        if inst_id:
            try:
                from src.action.instances import create_permanent
                given = {
                    "id": job_id or "",
                    "source": source or "gui",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "text": f"step {i}: {res.get('task')}",
                    "meta": {"step": i, "job_id": job_id, "instance_id": inst_id},
                }
                res["instance"] = str(create_permanent(inst_id, given, res))
            except Exception as e:
                res["instance_error"] = str(e)

        results.append(res)
        _write_trace(instance_dir, i, res)
        if inst_id and res.get("instance"):
            _write_trace(res["instance"], i, res)

        if res.get("status") == "ok":
            prev_output = res.get("output", "")
            outputs[i] = prev_output
        else:
            status = "error"
            failed_at = i
            if policy == FAIL_FAST:
                break

    return {
        "status": status,
        "steps": results,
        "failed_at": failed_at,
        "total_ms": int((time.monotonic() - started) * 1000),
        "error_kind": "step_failed" if status == "error" else "ok",
        "output": results[-1].get("output", "") if results else "",
        "error": next((r.get("error", "") for r in results if r.get("status") == "error"), ""),
    }


def _write_trace(instance_dir: Path | None, step_no: int, result: dict) -> None:
    """Persist one step's result under the instance — Phase 8."""
    if not instance_dir:
        return
    try:
        d = Path(instance_dir) / "steps"
        d.mkdir(parents=True, exist_ok=True)
        slim = {
            "step": step_no,
            "task": result.get("task"),
            "status": result.get("status"),
            "error_kind": result.get("error_kind"),
            "exit_code": result.get("exit_code"),
            "attempts": result.get("attempts"),
            "runs": result.get("runs"),
            "output": (result.get("output") or "")[:2000],
            "error": (result.get("error") or "")[:2000],
        }
        (d / f"{step_no}.json").write_text(json.dumps(slim, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass  # trace is best-effort, never fail a run over it


def write_job_trace(instance_dir: Path | str | None, results: list[dict]) -> None:
    """Persist a completed job's per-step trace into its instance — Phase 8.
    Called after the instance exists (steps run before it is created).
    """
    if not instance_dir or not results:
        return
    for res in results:
        if res.get("step"):
            _write_trace(Path(instance_dir), res["step"], res)


def run_job(
    text: str,
    *,
    job_id: str | None = None,
    source: str | None = None,
    policy: str = DEFAULT_POLICY,
    instance_dir: Path | None = None,
    validate_task=None,
) -> dict:
    """Parse a PLAN from opencode output and run it as one job — Phase 8.
    Validates every task and every `uses` ref BEFORE step 1 runs, so a bad
    plan costs nothing. Returns the same shape as run_steps(), plus `plan`.
    """
    if validate_task is None:
        from src.cli.opencode import validate_task as _vt
        validate_task = _vt

    steps = parse_plan(text)
    if not steps:
        return {
            "status": "error",
            "plan": [],
            "steps": [],
            "failed_at": 0,
            "total_ms": 0,
            "error_kind": "parse_error",
            "error": "no PLAN found in opencode output",
            "output": "",
        }

    check = validate(steps, validate_task)
    if not check["ok"]:
        logbook.record(
            check["steps"][0].get("task", "") if check["steps"] else "",
            "error", job_id=job_id, source=source, attempt=1, attempts=1,
            error=check["error"], error_kind=check["error_kind"], exit_code=1,
        )
        return {
            "status": "error",
            "plan": steps,
            "steps": [],
            "failed_at": 0,
            "total_ms": 0,
            "error_kind": check["error_kind"],
            "error": check["error"],
            "output": "",
        }

    out = run_steps(
        check["steps"], job_id=job_id, source=source, policy=policy, instance_dir=instance_dir
    )
    out["plan"] = steps
    return out