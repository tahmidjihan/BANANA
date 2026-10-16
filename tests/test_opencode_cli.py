"""opencode CLI adapter tests — WORKFLOW.md outstanding item: real-run verification

These cover the argv construction that the --mock path never exercises. The
`--file` ordering bug shipped undetected through the entire mock suite because
mock returns before any command is built.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cli.opencode import build_cmd, parse_output, validate_task


def test_message_passed_positionally_without_file():
    cmd = build_cmd("hello world")
    assert cmd[-1] == "hello world"
    assert "--file" not in cmd


def test_file_flag_comes_after_message():
    """Regression: --file is a yargs ARRAY option. Before the fix the argv was
    [--file, path, message], so opencode tried to open the message as a file
    and every real run failed with 'File not found: <prompt>'."""
    cmd = build_cmd("do the thing", use_file=True, tmp_path="/tmp/p.md")
    file_i = cmd.index("--file")
    msg_i = cmd.index("do the thing")
    assert msg_i < file_i, "--file must come after the message"
    assert cmd[file_i + 1] == "/tmp/p.md"


def test_large_prompt_is_truncated_when_attached():
    big = "x" * 9000
    cmd = build_cmd(big, use_file=True, tmp_path="/tmp/p.md")
    assert cmd[-3] == big[:200], "message truncated to a summary"
    assert big not in cmd, "full prompt never goes in argv"


def test_model_flag_included():
    assert "--model" in build_cmd("hi", model="ollama/qwen2.5-coder:3b")


def test_no_model_flag_when_unset():
    assert "--model" not in build_cmd("hi", model=None)


def test_auto_and_json_flags_always_present():
    cmd = build_cmd("hi")
    assert cmd[:3] == ["opencode", "run", "--format"]
    assert "json" in cmd
    assert "--auto" in cmd


# --- parse_output: shapes a real opencode run actually emits ---

def test_parse_real_jsonl_task():
    raw = (
        '{"type":"step_start","part":{"id":"p1","type":"step-start"}}\n'
        '{"type":"text","part":{"type":"text","text":"TASK: echo-demo\\nARGS: {\\"msg\\": \\"hi\\"}"}}\n'
        '{"type":"step_finish","part":{"type":"step-finish","reason":"stop"}}\n'
    )
    out = parse_output(raw)
    assert out["task"] == "echo-demo"
    assert out["args"] == {"msg": "hi"}


def test_parse_real_jsonl_plan():
    raw = (
        '{"type":"text","part":{"type":"text",'
        '"text":"PLAN:\\n- step 1: echo-demo {\\"msg\\":\\"a\\"}\\n- step 2: count-words uses: $prev"}}\n'
    )
    out = parse_output(raw)
    assert [s["task"] for s in out["steps"]] == ["echo-demo", "count-words"]


def test_parse_chat_text_when_no_task():
    raw = '{"type":"text","part":{"type":"text","text":"Hi! I can run echo-demo."}}\n'
    out = parse_output(raw)
    assert out["task"] is None
    assert out["chat_text"].startswith("Hi!")


def test_parse_error_output_yields_no_task():
    """A real run that errors must not be mistaken for a task."""
    raw = "\nError: File not found: # SYSTEM\nsome prompt text\n"
    out = parse_output(raw)
    assert out["task"] is None
    assert out["steps"] == []


def test_validate_task_rejects_traversal():
    assert validate_task("../../etc") is False
    assert validate_task("") is False


def test_validate_task_accepts_real_task():
    assert validate_task("echo-demo") is True