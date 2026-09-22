"""MEMORY.md — recent memories, auto-updated after each turn
File: ROOT/MEMORY.md (also container /app/MEMORY.md)
Keeps: User, How to run tasks, Recent Topics, Recent Task Runs, Preferences
Loaded into prompt CONTEXT, editable via UI and via agent write.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEM_PATH = ROOT / "MEMORY.md"
CONTAINER_MEM = Path("/app/MEMORY.md")

MAX_CHARS = 4000
MAX_TOPICS = 12
MAX_RUNS = 8

TEMPLATE = """# MEMORY.md — Banana's Recent Memories

> Auto-updated after each turn. Agent reads this every prompt. Keep minimal — file-based, 4k max.

## User
- Owner: Personal user. Minimal output, no fluff.
- What Banana knows: (add as you learn)

## How to Run Tasks
- `echo-demo`: `bash tasks/echo-demo/run.sh '{"msg":"hello"}'` or `run echo-demo hello`
- `hello-py`: `python tasks/hello-py/run.py '{"msg":"hello"}'`
- `count-words`: `bash tasks/count-words/run.sh '{"msg":"hello world"}'` → `2`
- `reverse-text`: `bash tasks/reverse-text/run.sh '{"msg":"hello"}'` → `olleh`
- `title-case`: `bash tasks/title-case/run.sh '{"msg":"hello world"}'` → `Hello World`
- `daily-news`: `python tasks/daily-news/run.py '{"dry_run":true}'`

## Recent Topics
- (auto) No topics yet

## Recent Task Runs
- (auto) No runs yet

## Preferences
- Language: English (concise)
- Style: Brutal minimalist, black/white, borders
- Port: 4242 (42×101 double Answer)

## Notes
- Chats: `instances/chats/{id}/chat.json`
- Creds: `config/creds.json`
"""

def _mem_path() -> Path:
    if CONTAINER_MEM.exists() or Path("/app").exists():
        # ensure parent
        return CONTAINER_MEM
    return MEM_PATH

def ensure_memory():
    p=_mem_path()
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(TEMPLATE, encoding="utf-8")
    return p

def load_memory(max_chars: int = 3000) -> str:
    p=_mem_path()
    if not p.exists():
        ensure_memory()
    try:
        txt=p.read_text(encoding="utf-8").strip()
        if len(txt) > max_chars:
            # keep header + truncate body
            txt=txt[:max_chars] + "\n\n[truncated]"
        return txt
    except Exception:
        return ""

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def _parse_sections(text: str) -> dict:
    # split by ## headers
    sections={}
    current=None
    buf=[]
    for line in text.splitlines():
        m=re.match(r'^##\s+(.+)$', line)
        if m:
            if current:
                sections[current]="\n".join(buf).strip()
            current=m.group(1).strip()
            buf=[]
        else:
            buf.append(line)
    if current:
        sections[current]="\n".join(buf).strip()
    return sections

def _render_sections(sections: dict) -> str:
    order=["User","How to Run Tasks","Recent Topics","Recent Task Runs","Preferences","Notes"]
    # keep any extra sections at end
    out=["# MEMORY.md — Banana's Recent Memories",""," > Auto-updated after each turn. Agent reads this every prompt. Keep minimal — file-based, 4k max.",""]
    for key in order:
        if key in sections:
            out.append(f"## {key}")
            out.append(sections[key] or "(empty)")
            out.append("")
    for k,v in sections.items():
        if k not in order:
            out.append(f"## {k}")
            out.append(v)
            out.append("")
    return "\n".join(out).strip() + "\n"

def update_memory(given: dict, result: dict, created_tasks: list | None = None):
    """Append recent topic and task run to MEMORY.md, keep bounded"""
    try:
        p=ensure_memory()
        text=p.read_text(encoding="utf-8")
        sections=_parse_sections(text)

        # ensure sections exist
        for k in ["User","How to Run Tasks","Recent Topics","Recent Task Runs","Preferences","Notes"]:
            sections.setdefault(k, "")

        # Recent Topics — add current text
        user_text=(given.get("text") or "").strip()
        if user_text:
            topics=sections["Recent Topics"].splitlines()
            # filter placeholder
            topics=[t for t in topics if t.strip() and "(auto)" not in t]
            entry=f"- [{_now()}] {user_text[:120]}"
            # avoid duplicate consecutive
            if not topics or topics[0] != entry:
                topics.insert(0, entry)
            topics=topics[:MAX_TOPICS]
            sections["Recent Topics"]="\n".join(topics)

        # Recent Task Runs
        task=(result or {}).get("task")
        status=(result or {}).get("status")
        output=(result or {}).get("output","")[:120].replace("\n"," ")
        if task or (status in ("ok","chat","created")):
            runs=sections["Recent Task Runs"].splitlines()
            runs=[r for r in runs if r.strip() and "(auto)" not in r]
            if task:
                entry=f"- [{_now()}] {task} → {output[:80]}"
            elif status=="chat":
                entry=f"- [{_now()}] chat: {user_text[:60]} → {output[:60]}"
            else:
                entry=f"- [{_now()}] {status}: {user_text[:60]}"
            if created_tasks:
                entry+= f" [+{','.join(created_tasks)}]"
            if not runs or runs[0] != entry:
                runs.insert(0, entry)
            runs=runs[:MAX_RUNS]
            sections["Recent Task Runs"]="\n".join(runs)

        # How to Run Tasks — keep static, but ensure it exists (don't auto-append every time)
        # User — could be updated via explicit instruction, not auto here

        new_text=_render_sections(sections)
        if len(new_text) > MAX_CHARS:
            # truncate topics/runs oldest
            # simple: cut to 3800
            new_text=new_text[:3800] + "\n\n[truncated to 4k]"
        p.write_text(new_text, encoding="utf-8")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("memory update failed: %s", e)
