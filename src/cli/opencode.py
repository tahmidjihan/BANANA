"""Opencode wrapper — plan.md:100-113, WORKFLOW.md:57-69
Prompt -> opencode (opencode run) -> parsed TASK
Actual CLI: opencode run [message..] --format json|default  (verified 1.18.31)
No --prompt-file flag — we pass prompt as positional message arg.
"""
import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "tasks"
# container path
CONTAINER_TASKS = Path("/app/tasks")

TIMEOUT = 120


def _tasks_dir() -> Path:
    # prefer container path if exists else host ROOT/tasks
    if CONTAINER_TASKS.exists():
        return CONTAINER_TASKS
    return TASKS_DIR


def parse_output(text: str) -> dict:
    """Parse opencode output for TASK — WORKFLOW.md:65
    Supports:
      TASK: <name>
      ARGS: {...}
      JSON {"action":"run_task","task":"...","args":{}} or {"task":"..."}
      ```json blocks
    Returns {task, args, raw}
    """
    raw = text or ""
    task = None
    args = {}

    # 1) TASK: line
    m = re.search(r"TASK:\s*([A-Za-z0-9_\-\.\/]+)", raw, re.IGNORECASE)
    if m:
        task = m.group(1).strip().strip("/")

    # ARGS: JSON line
    m_args = re.search(r"ARGS:\s*(\{.*\})", raw, re.DOTALL)
    if m_args:
        try:
            args = json.loads(m_args.group(1).strip())
        except Exception:
            pass

    # 2) JSON object with task/action
    if not task:
        # find all json blocks
        for block in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL):
            try:
                obj = json.loads(block)
                if "task" in obj:
                    task = obj["task"]
                    args = obj.get("args", obj.get("ARGS", args))
                    break
                if "action" in obj and "task" in obj.get("action", {}):
                    task = obj["action"]["task"]
                    break
            except Exception:
                continue
        # also try bare JSON lines
        if not task:
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        obj = json.loads(line)
                        if "task" in obj:
                            task = obj["task"]
                            args = obj.get("args", args)
                            break
                    except Exception:
                        continue

    return {"task": task, "args": args if isinstance(args, dict) else {}, "raw": raw}


def validate_task(task: str) -> bool:
    if not task:
        return False
    # prevent path traversal
    if ".." in task or task.startswith("/"):
        return False
    td = _tasks_dir() / task
    return td.exists() and td.is_dir()


def run(prompt: str, timeout: int = TIMEOUT, retry: int = 1, mock: bool = False) -> dict:
    """Run opencode with prompt — WORKFLOW.md:62
    Returns {raw_text, exit_code, task, args, error, parsed}
    mock=True returns fake success without calling opencode (for tests without auth)
    """
    if mock or os.getenv("MOCK_OPENCODE") == "1":
        fake = "TASK: echo-demo\nARGS: {\"msg\": \"hello from mock\"}"
        parsed = parse_output(fake)
        return {
            "raw_text": fake,
            "exit_code": 0,
            "task": parsed["task"],
            "args": parsed["args"],
            "error": None,
            "parsed": parsed,
        }

    if not prompt or not prompt.strip():
        return {"raw_text": "", "exit_code": 1, "task": None, "args": {}, "error": "empty prompt", "parsed": None}

    # Build command — opencode run --format json "<prompt>"
    # Use tempfile + --file if prompt very large (>8000 chars) to avoid ARG_MAX
    use_file = len(prompt) > 8000
    tmp_path = None

    def build_cmd():
        base = ["opencode", "run", "--format", "json"]
        # optional model from env
        model = os.getenv("OPENCODE_MODEL")
        if model:
            base.extend(["--model", model])
        if use_file and tmp_path:
            base.extend(["--file", tmp_path, prompt[:200]])  # file attached + short message
        else:
            base.append(prompt)
        return base

    last_result = None
    for attempt in range(retry + 1):
        cmd = None
        try:
            if use_file:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
                    f.write(prompt)
                    tmp_path = f.name
                cmd = build_cmd()
            else:
                cmd = build_cmd()

            logger.info("opencode attempt %d: %s", attempt + 1, " ".join(cmd[:4]) + " ...")
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(ROOT),
            )
            raw = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
            parsed = parse_output(raw)
            task = parsed["task"]
            # validate task exists if found
            if task and not validate_task(task):
                logger.warning("task '%s' not found in %s", task, _tasks_dir())

            result = {
                "raw_text": raw,
                "exit_code": proc.returncode,
                "task": task,
                "args": parsed["args"],
                "error": None if proc.returncode == 0 else f"exit {proc.returncode}",
                "parsed": parsed,
            }
            last_result = result
            if proc.returncode == 0:
                return result
            # retry on non-zero unless last attempt
            if attempt < retry:
                logger.warning("opencode failed, retrying...")
                continue
            return result

        except subprocess.TimeoutExpired:
            err = f"timeout after {timeout}s"
            logger.error(err)
            last_result = {"raw_text": "", "exit_code": 124, "task": None, "args": {}, "error": err, "parsed": None}
            if attempt < retry:
                continue
            return last_result
        except FileNotFoundError:
            err = "opencode binary not found"
            return {"raw_text": "", "exit_code": 127, "task": None, "args": {}, "error": err, "parsed": None}
        except Exception as e:
            err = str(e)
            return {"raw_text": "", "exit_code": 1, "task": None, "args": {}, "error": err, "parsed": None}
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
    return last_result or {"raw_text": "", "exit_code": 1, "task": None, "args": {}, "error": "unknown", "parsed": None}
