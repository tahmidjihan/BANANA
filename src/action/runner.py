"""Runner — WORKFLOW.md Phase 7

Wraps execute() so the pipeline never crashes on a task error. Decides what to
do after a give-up: abort the run (fail_fast) or carry on (continue) and report
at the end. Multi-step job support (Phase 8) builds on run_steps().
"""
from src.action import logbook
from src.action.executor import execute

FAIL_FAST = "fail_fast"
CONTINUE = "continue"
DEFAULT_POLICY = FAIL_FAST


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


def run_steps(
    steps: list[dict],
    *,
    job_id: str | None = None,
    source: str | None = None,
    policy: str = DEFAULT_POLICY,
    max_steps: int = 10,
    budget_seconds: int = 300,
) -> dict:
    """Run an ordered list of steps. Phase 8 builds on this.
    steps: [{"task": name, "args": {...}, "uses": "<prev output>"}]
    Returns {status, steps: [...], failed_at, total_ms, error_kind}
    """
    import time

    started = time.monotonic()
    results: list[dict] = []
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
        }

    for i, step in enumerate(steps, start=1):
        if time.monotonic() - started > budget_seconds:
            status = "error"
            failed_at = i
            results.append({
                "step": i, "task": step.get("task", ""), "status": "error",
                "error_kind": "budget_exceeded", "error": f"job budget {budget_seconds}s exhausted",
            })
            break

        step_args = dict(step.get("args") or {})
        uses = step.get("uses")
        if uses:
            step_args.setdefault("_prev_output", prev_output[:2000])

        res = run_task(step.get("task", ""), step_args, job_id=job_id, source=source)
        res["step"] = i
        results.append(res)

        if res.get("status") == "ok":
            prev_output = res.get("output", "")
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
    }