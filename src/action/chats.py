"""Chats — file-based chat history, agent aware
Store: instances/chats/{id}/chat.json + messages
Not temp — permanent until deleted. Agent can create/delete via write/shell.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHATS_DIR = ROOT / "instances" / "chats"
CONTAINER_CHATS = Path("/app/instances/chats")

def _chats_dir() -> Path:
    if CONTAINER_CHATS.exists() or Path("/app").exists():
        # if container path exists or /app exists, use container
        # ensure parent exists
        CONTAINER_CHATS.mkdir(parents=True, exist_ok=True)
        return CONTAINER_CHATS
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    return CHATS_DIR

def _chat_path(chat_id: str) -> Path:
    if not chat_id or "/" in chat_id or ".." in chat_id:
        raise ValueError(f"invalid chat_id: {chat_id}")
    return _chats_dir() / chat_id

def _chat_file(chat_id: str) -> Path:
    return _chat_path(chat_id) / "chat.json"

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def create_chat(title: str | None = None) -> dict:
    cid = str(uuid.uuid4())
    now = _now_iso()
    data = {
        "id": cid,
        "title": (title or "New Chat").strip()[:80] or "New Chat",
        "created_at": now,
        "updated_at": now,
        "messages": []
    }
    p = _chat_file(cid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data

def list_chats() -> list[dict]:
    base = _chats_dir()
    if not base.exists():
        return []
    out=[]
    for child in base.iterdir():
        if child.name.startswith(".") or not child.is_dir():
            continue
        jf = child / "chat.json"
        if not jf.exists():
            continue
        try:
            data=json.loads(jf.read_text(encoding="utf-8"))
            # summary
            msgs=data.get("messages",[])
            last = msgs[-1].get("text","")[:60] if msgs else ""
            out.append({
                "id": data.get("id", child.name),
                "title": data.get("title","Untitled"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "message_count": len(msgs),
                "preview": last,
            })
        except Exception:
            continue
    # sort by updated_at desc
    out.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return out

def get_chat(chat_id: str) -> dict | None:
    jf=_chat_file(chat_id)
    if not jf.exists():
        return None
    try:
        return json.loads(jf.read_text(encoding="utf-8"))
    except Exception:
        return None

def delete_chat(chat_id: str) -> bool:
    import shutil
    p=_chat_path(chat_id)
    if not p.exists():
        return False
    shutil.rmtree(p)
    return True

def rename_chat(chat_id: str, title: str) -> dict | None:
    data=get_chat(chat_id)
    if not data:
        return None
    data["title"]=title.strip()[:80] or data["title"]
    data["updated_at"]=_now_iso()
    _chat_file(chat_id).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data

def add_message(chat_id: str, role: str, text: str, given: dict | None = None, result: dict | None = None) -> dict | None:
    data=get_chat(chat_id)
    if not data:
        return None
    msg={
        "role": role,
        "text": text,
        "timestamp": _now_iso(),
    }
    if given:
        msg["given"]=given
    if result:
        # store minimal result to avoid huge cli_raw bloat, but keep output
        msg["result"]={"output": result.get("output"), "status": result.get("status"), "task": result.get("task"), "created_tasks": result.get("created_tasks")}
    data["messages"].append(msg)
    data["updated_at"]=_now_iso()
    # auto-title from first user message if still "New Chat"
    if data["title"]=="New Chat" and role=="user" and text.strip():
        data["title"]=text.strip()[:40]
    # truncate if too long (keep last 100 messages)
    if len(data["messages"])>200:
        data["messages"]=data["messages"][-200:]
    _chat_file(chat_id).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data

def get_messages(chat_id: str, limit: int = 50) -> list[dict]:
    data=get_chat(chat_id)
    if not data:
        return []
    msgs=data.get("messages",[])
    return msgs[-limit:]

def ensure_chat(chat_id: str | None) -> dict:
    if chat_id:
        c=get_chat(chat_id)
        if c:
            return c
    # create new
    return create_chat()
