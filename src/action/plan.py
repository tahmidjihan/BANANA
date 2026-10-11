"""Plan parsing — WORKFLOW.md Phase 8

Turns a PLAN: block (or JSON plan/steps object) from opencode output into an
ordered list of steps, and validates the WHOLE plan before step 1 runs so a
typo in step 4 does not waste the first three.

Format (one step per line):
    PLAN:
    - step 1: echo-demo {"msg": "hello"}
    - step 2: reverse-text {"msg": "seed"} uses: "$prev"
    - step 3: count-words uses: step1

`uses` binds the referenced step's stdout into the next step's args:
    $prev / prev      -> previous step's output
    stepN / <stepN>   -> output of step N
    outputN / <outputN>
Bound value lands in the step's args as "_prev_output" (truncated) so a task
can read it, and as "input" when the step declared no explicit args.

JSON form also accepted:
    {"plan": [{"task": "echo-demo", "args": {"msg": "hi"}}]}
    {"steps": [...]}
"""
import json
import re

MAX_STEPS = 10
MAX_CHAINED_CHARS = 2000

# "- step 1: task-name {json args} uses: step1"  (number/args/uses all optional)
_STEP_RE = re.compile(
    r"""^\s*(?:[-*]\s*)?                        # optional list bullet
        (?:step\s*(\d+)\s*[.):\-]\s*)?         # optional step number
        ([A-Za-z0-9_\-\.]+)\s*                 # task name
        (\{.*\})?\s*                           # optional inline JSON args
        (?:uses?\s*[:=]\s*"?([A-Za-z0-9_$<>.\-]+)"?)?\s*   # optional uses ref
        $""",
    re.IGNORECASE | re.VERBOSE,
)


def _balanced_json(text: str) -> str | None:
    """Extract the first balanced {...} so nested args survive."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_plan(text: str) -> list[dict]:
    """Extract steps from opencode output. Returns [] when there is no plan.
    Never raises — malformed lines are skipped.
    """
    if not text:
        return []

    steps = _from_json(text)
    if steps:
        return steps

    return _from_lines(text)


def _from_json(text: str) -> list[dict]:
    """{"plan": [...]} / {"steps": [...]} in a fenced or bare JSON block."""
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            blocks.append(line)

    for block in blocks:
        obj = _try_json(block)
        if not isinstance(obj, dict):
            continue
        raw_steps = obj.get("plan") or obj.get("steps")
        if not isinstance(raw_steps, list):
            continue
        out = []
        for s in raw_steps:
            if isinstance(s, str):
                parsed = _one_step(s)
                if parsed:
                    out.append(parsed)
            elif isinstance(s, dict):
                task = s.get("task") or s.get("name")
                if not task:
                    continue
                args = s.get("args") if isinstance(s.get("args"), dict) else {}
                out.append({
                    "task": str(task).strip(),
                    "args": args,
                    "uses": s.get("uses") or s.get("use") or None,
                })
        if out:
            return out
    return []


def _try_json(block: str):
    try:
        return json.loads(block)
    except Exception:
        return None


_STEP_PREFIX = re.compile(
    r"^\s*(?:[-*]\s*|(?:step\s*)?\d+\s*[.):\-]\s*)", re.IGNORECASE
)


def _one_step(line: str) -> dict | None:
    # A bare word like "Done." would otherwise match _STEP_RE as a task name.
    # Require an explicit bullet or step number so prose ends the block.
    if not _STEP_PREFIX.match(line):
        return None
    m = _STEP_RE.match(line)
    if not m:
        return None
    _, task, args_raw, uses = m.groups()
    args = {}
    if args_raw:
        parsed = _try_json(args_raw) or _try_json(_balanced_json(args_raw) or "")
        if isinstance(parsed, dict):
            args = parsed
    return {"task": task.strip(), "args": args, "uses": uses or None}


def _from_lines(text: str) -> list[dict]:
    """Read the PLAN: block. Lines outside it are ignored so prose that
    happens to mention a task name is not mistaken for a step."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*PLAN\s*:?\s*$", line, re.IGNORECASE):
            start = i + 1
            break
    if start is None:
        return []

    steps: list[dict] = []
    for line in lines[start:]:
        if not line.strip():
            if steps:
                break
            continue
        if re.match(r"^\s*(TASK|ARGS)\s*:", line, re.IGNORECASE):
            # Single-step format leaking into a PLAN block. Only bail before any
            # real steps are seen — a trailing TASK: after steps is harmless.
            return [] if not steps else steps
        parsed = _one_step(line)
        if parsed:
            steps.append(parsed)
            continue
        if steps:
            # a non-step line after real steps ends the block
            break
    return steps


def validate(steps: list[dict], valid_task) -> dict:
    """Validate the whole plan before running anything.
    valid_task: callable(task_name) -> bool
    Returns {ok, error, error_kind, steps}
    """
    if not steps:
        return {"ok": False, "error": "no steps parsed", "error_kind": "parse_error", "steps": []}

    if len(steps) > MAX_STEPS:
        return {
            "ok": False,
            "error": f"{len(steps)} steps exceeds max {MAX_STEPS}",
            "error_kind": "too_many_steps",
            "steps": steps,
        }

    missing = [s["task"] for s in steps if not valid_task(s["task"])]
    if missing:
        return {
            "ok": False,
            "error": f"unknown task(s): {', '.join(sorted(set(missing)))}",
            "error_kind": "not_found",
            "steps": steps,
        }

    bad_refs = []
    for i, s in enumerate(steps, start=1):
        ref = s.get("uses")
        if not ref:
            continue
        if not _resolve_ref(ref, i, len(steps)):
            bad_refs.append(f"step {i}: {ref}")
    if bad_refs:
        return {
            "ok": False,
            "error": "unresolvable uses ref: " + "; ".join(bad_refs),
            "error_kind": "parse_error",
            "steps": steps,
        }

    return {"ok": True, "error": "", "error_kind": "ok", "steps": steps}


def _resolve_ref(ref: str, step_no: int, total: int) -> int | None:
    """Return the 1-based step number a uses-ref points at, or None."""
    r = str(ref).strip().strip("\"<>").lower()
    if r in ("$prev", "prev", "previous", "$last", "last", "output"):
        return step_no - 1 if step_no > 1 else None
    m = re.fullmatch(r"(?:step|output|\$)?\s*(\d+)", r)
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= total else None
    return None


def bind_args(steps: list[dict], outputs: dict[int, str]) -> None:
    """Resolve `uses` refs against prior step outputs, in place.
    Bound value is truncated to MAX_CHAINED_CHARS.
    """
    for i, s in enumerate(steps, start=1):
        ref = s.get("uses")
        if not ref:
            continue
        src = _resolve_ref(ref, i, len(steps))
        if not src:
            continue
        val = (outputs.get(src) or "")[:MAX_CHAINED_CHARS]
        args = s.setdefault("args", {})
        if not args:
            args["msg"] = val
        args["_prev_output"] = val