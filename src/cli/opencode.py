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
      v2 JSONL: {"type":"text","part":{"text":"TASK: ..."}} — decodes first
    Returns {task, args, raw, decoded_text, chat_text}
    """
    raw = text or ""
    task = None
    args = {}

    # --- v2 JSONL handling: extract decoded text parts ---
    # opencode --format json emits JSONL where final answer is in part.text (escaped).
    # Decode each line, collect text pieces, then search on decoded combined.
    decoded_parts: list[str] = []
    has_jsonl = False
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            # opencode v2: {"type":"text","part":{"text":"..."}}
            part = obj.get("part") or {}
            t = part.get("text")
            if isinstance(t, str) and t.strip():
                decoded_parts.append(t)
                has_jsonl = True
                continue
            # also direct {"type":"text","text":"..."} fallback
            if obj.get("type") == "text" and isinstance(obj.get("text"), str):
                decoded_parts.append(obj["text"])
                has_jsonl = True
        except Exception:
            continue

    # search_text is decoded if we found JSONL text, else raw
    search_text = "\n".join(decoded_parts) if has_jsonl else raw

    # 1) TASK: line
    m = re.search(r"TASK:\s*([A-Za-z0-9_\-\.\/]+)", search_text, re.IGNORECASE)
    if m:
        task = m.group(1).strip().strip("/")

    # ARGS: JSON line — use decoded search_text so {"msg":"hello"} is valid JSON
    m_args = re.search(r"ARGS:\s*(\{.*?\})", search_text, re.DOTALL)
    if m_args:
        try:
            args = json.loads(m_args.group(1).strip())
        except Exception:
            pass
    # fallback: also scan raw if decoded didn't have ARGS (e.g. mock plain text)
    if not args and search_text is not raw:
        m2 = re.search(r"ARGS:\s*(\{.*?\})", raw, re.DOTALL)
        if m2:
            try:
                args = json.loads(m2.group(1).strip())
            except Exception:
                pass

    # 2) JSON object with task/action (search both decoded and raw)
    for src in (search_text, raw) if has_jsonl else (raw,):
        if task:
            break
        # find all json blocks
        for block in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", src, re.DOTALL):
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
            for line in src.splitlines():
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

    # chat_text = last decoded text chunk when no TASK (for greetings / no_task)
    chat_text = ""
    if has_jsonl and decoded_parts:
        # last part is usually final answer
        chat_text = decoded_parts[-1].strip()
        # if it still contains TASK line, don't use as chat
        if task and "TASK:" in chat_text:
            # find non-TASK decoded parts
            non_task = [p for p in decoded_parts if "TASK:" not in p]
            chat_text = (non_task[-1] if non_task else "").strip()
    elif not has_jsonl and not task:
        chat_text = raw.strip()[:2000]

    return {
        "task": task,
        "args": args if isinstance(args, dict) else {},
        "raw": raw,
        "decoded_text": search_text,
        "chat_text": chat_text,
    }


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
        # dynamic mock: pick task mentioned in GIVEN text, fallback echo-demo
        hint_task = "echo-demo"
        hint_msg = "hello from mock"
        given_text = prompt  # fallback search all
        # extract GIVEN json block to prefer actual user text
        m_given = re.search(r"# GIVEN.*?```json(.*?)```", prompt, re.DOTALL)
        if m_given:
            try:
                given_obj = json.loads(m_given.group(1).strip())
                given_text = given_obj.get("text", "") + " " + json.dumps(given_obj.get("meta", {}))
            except Exception:
                pass
        try:
            td = _tasks_dir()
            if td.exists():
                for cand in sorted(td.iterdir()):
                    if cand.is_dir() and cand.name in given_text:
                        hint_task = cand.name
                        idx = given_text.find(cand.name)
                        after = given_text[idx + len(cand.name):].strip().splitlines()[0][:60]
                        after = after.strip(' "\'{}:,')
                        if after and len(after) > 2:
                            hint_msg = after[:40]
                        break
        except Exception:
            pass
        m = re.search(r'"msg"\s*:\s*"([^"]+)"', prompt)
        if m:
            hint_msg = m.group(1)
        fake = f"TASK: {hint_task}\nARGS: {{\"msg\": \"{hint_msg}\"}}"
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
                "chat_text": parsed.get("chat_text", ""),
                "decoded_text": parsed.get("decoded_text", ""),
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
