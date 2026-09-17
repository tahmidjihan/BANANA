"""Detector — plan.md:54-63, WORKFLOW.md:30-39
Generates normalized Given: {id, source, timestamp, text, meta}
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from croniter import croniter
except ImportError:  # allow minimal without croniter during early dev
    croniter = None

SCHEMA_PATH = Path(__file__).with_name("schema.json")
VALID_SOURCES = {"gui", "telegram", "cron"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def validate(given: dict) -> bool:
    """Minimal validation against schema rules without jsonschema dep."""
    if not isinstance(given, dict):
        raise ValueError("Given must be dict")
    for k in ("id", "source", "timestamp", "text", "meta"):
        if k not in given:
            raise ValueError(f"missing required field: {k}")
    if given["source"] not in VALID_SOURCES:
        raise ValueError(f"invalid source: {given['source']}")
    if not isinstance(given["text"], str):
        raise ValueError("text must be string")
    if not isinstance(given["meta"], dict):
        raise ValueError("meta must be dict")
    # id & timestamp basic checks
    try:
        uuid.UUID(given["id"])
    except Exception:
        raise ValueError("invalid id UUID")
    try:
        datetime.fromisoformat(given["timestamp"])
    except Exception:
        raise ValueError("invalid timestamp ISO8601")
    return True


def from_message(text: str, source: str = "gui", meta_extra: dict | None = None) -> dict:
    """Create Given from user message — WORKFLOW.md:34"""
    if not text or not text.strip():
        raise ValueError("text must be non-empty")
    source = source.lower().strip()
    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}")
    if source == "cron":
        raise ValueError("use from_cron() for cron source")
    given = {
        "id": _new_id(),
        "source": source,
        "timestamp": _now_iso(),
        "text": text.strip(),
        "meta": dict(meta_extra or {}),
    }
    validate(given)
    return given


def from_cron(cron_expr: str, task_ref: str = "", meta_extra: dict | None = None) -> dict:
    """Create Given from CRON — WORKFLOW.md:35"""
    if not cron_expr or not cron_expr.strip():
        raise ValueError("cron_expr must be non-empty")
    cron_expr = cron_expr.strip()
    if croniter is None:
        raise RuntimeError("croniter not installed — pip install croniter")
    # validate expr
    try:
        itr = croniter(cron_expr, datetime.now(timezone.utc))
        next_run = itr.get_next(datetime).isoformat()
    except Exception as e:
        raise ValueError(f"invalid cron_expr '{cron_expr}': {e}") from e

    if not task_ref or not task_ref.strip():
        # allow empty task_ref but warn via meta
        task_ref = task_ref.strip() if task_ref else ""

    given = {
        "id": _new_id(),
        "source": "cron",
        "timestamp": _now_iso(),
        "text": task_ref.strip() or cron_expr,
        "meta": {
            "cron_expr": cron_expr,
            "task_ref": task_ref.strip(),
            "next_run": next_run,
            **(meta_extra or {}),
        },
    }
    validate(given)
    return given


def to_json(given: dict, pretty: bool = True) -> str:
    validate(given)
    return json.dumps(given, indent=2 if pretty else None, ensure_ascii=False)


def save(given: dict, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(to_json(given), encoding="utf-8")
    return p
