"""Instances — WORKFLOW.md:84-87, plan.md:137-169
Temp TTL 72h, permanent until deleted. File-based, no DB (AGENTS.md:79)
"""
import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTANCES_TEMP = ROOT / "instances" / "temp"
INSTANCES_PERM = ROOT / "instances" / "permanent"
# container paths
CONTAINER_TEMP = Path("/app/instances/temp")
CONTAINER_PERM = Path("/app/instances/permanent")

TTL_SECONDS = 72 * 3600


def _temp_dir() -> Path:
    if CONTAINER_TEMP.exists() or Path("/app").exists():
        return CONTAINER_TEMP
    return INSTANCES_TEMP


def _perm_dir() -> Path:
    if CONTAINER_PERM.exists() or Path("/app").exists():
        return CONTAINER_PERM
    return INSTANCES_PERM


def create_temp(given: dict, result: dict, keep: bool = False) -> Path:
    """Create temp instance — WORKFLOW.md:85"""
    base = _temp_dir()
    base.mkdir(parents=True, exist_ok=True)
    iid = str(uuid.uuid4())
    d = base / iid
    d.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    ctx = {
        "id": iid,
        "created_at": now,
        "keep": keep,
        "given": given,
        "result": result,
    }
    (d / "context.json").write_text(json.dumps(ctx, indent=2, ensure_ascii=False), encoding="utf-8")
    # TASKS ref
    task = (result or {}).get("task") or (given.get("meta") or {}).get("task_ref") or ""
    if task:
        (d / "TASKS").write_text(task, encoding="utf-8")
    return d


def create_permanent(id_: str, given: dict, result: dict) -> Path:
    """Create permanent instance — WORKFLOW.md:86"""
    base = _perm_dir()
    base.mkdir(parents=True, exist_ok=True)
    if not id_ or "/" in id_ or ".." in id_:
        raise ValueError(f"invalid permanent id: {id_}")
    d = base / id_
    d.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    ctx = {
        "id": id_,
        "created_at": now,
        "given": given,
        "result": result,
    }
    (d / "context.json").write_text(json.dumps(ctx, indent=2, ensure_ascii=False), encoding="utf-8")
    task = (result or {}).get("task") or ""
    if task:
        (d / "TASKS").write_text(task, encoding="utf-8")
    return d


def reap_temp(ttl: int = TTL_SECONDS, dry_run: bool = False) -> list[str]:
    """Reaper — WORKFLOW.md:87 deletes temp older than 72h unless keep:true
    Returns list of removed ids
    """
    base = _temp_dir()
    if not base.exists():
        return []
    now = time.time()
    removed = []
    for child in list(base.iterdir()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        ctx_path = child / "context.json"
        try:
            # check mtime if context missing
            if ctx_path.exists():
                data = json.loads(ctx_path.read_text(encoding="utf-8"))
                if data.get("keep") is True:
                    continue
                created = data.get("created_at")
                if created:
                    # parse iso
                    dt = datetime.fromisoformat(created)
                    age = (datetime.now(timezone.utc) - dt).total_seconds()
                else:
                    age = now - child.stat().st_mtime
            else:
                age = now - child.stat().st_mtime
            if age > ttl:
                if not dry_run:
                    import shutil
                    shutil.rmtree(child)
                removed.append(child.name)
        except Exception:
            # on parse error, fallback to mtime
            try:
                age = now - child.stat().st_mtime
                if age > ttl and not dry_run:
                    import shutil
                    shutil.rmtree(child)
                    removed.append(child.name)
            except Exception:
                continue
    return removed
