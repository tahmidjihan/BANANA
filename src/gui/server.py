"""Banana Web GUI server — React + Markdown, black/white brutal — 4242 = 42×101 double Answer
GET / -> static/index.html (React)
POST /api/chat {message, mock} -> pipeline
GET /api/tasks, /api/instances, /api/health, /api/creds, /api/config
POST /api/creds, /api/config
Run host: python -m src.gui.server --port 4242  # 42×101 double Answer — not 8080, brutal doubled
"""
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).parent / "static"
CONFIG_DIR = ROOT / "config"
CREDS_JSON = CONFIG_DIR / "creds.json"
ALLOWED_CONFIG = {"SOUL.md","AGENT.md","USER.md","ENTRY.md","SKILL.md"}

def _json(data, code=200):
    body = json.dumps(data, ensure_ascii=False).encode()
    return code, body, "application/json"

def _load_creds():
    try:
        from src.creds import load_creds
        return load_creds()
    except Exception:
        return {"OPENCODE_MODEL": os.getenv("OPENCODE_MODEL","opencode/big-pickle")}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"{self.client_address[0]} {format%args}", flush=True)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        # brutal minimalist dashboard alias
        if path in ("/brutal-minimalist-design", "/brutal-minimalist-design/"):
            f = STATIC / "index.html"
            if not f.exists():
                self.send_error(404, "index.html not found"); return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f.read_bytes()); return
        if path in ("/favicon.svg", "/favicon.ico"):
            f = STATIC / "favicon.svg"
            if f.exists():
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml")
                self.end_headers()
                self.wfile.write(f.read_bytes()); return
            self.send_error(404, "favicon not found"); return
        if path == "/" or path == "/index.html":
            f = STATIC / "index.html"
            if not f.exists():
                self.send_error(404, "index.html not found"); return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f.read_bytes()); return
        if path == "/api/health":
            creds=_load_creds()
            code, body, ctype = _json({"status":"ok","model": creds.get("OPENCODE_MODEL","opencode/big-pickle")})
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path == "/api/tasks":
            tasks_dir = ROOT / "tasks"
            tasks=[]
            if tasks_dir.exists():
                for d in sorted(tasks_dir.iterdir()):
                    if d.is_dir() and not d.name.startswith("."):
                        readme=(d / "README.md").read_text()[:800] if (d / "README.md").exists() else ""
                        has_sh=(d / "run.sh").exists(); has_py=(d / "run.py").exists()
                        tasks.append({"name":d.name,"readme":readme,"has_sh":has_sh,"has_py":has_py})
            code, body, ctype = _json({"tasks": tasks})
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path == "/api/instances":
            base = ROOT / "instances" / "temp"
            items=[]
            if base.exists():
                for p in sorted(base.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
                    if p.is_dir() and (p / "context.json").exists():
                        try:
                            data=json.loads((p / "context.json").read_text())
                            items.append({"id":p.name,"given":data.get("given"),"result":data.get("result"),"created_at":data.get("created_at"),
                                            "status":(data.get("result") or {}).get("status",""),
                                            "error_kind":(data.get("result") or {}).get("error_kind","")})
                        except: pass
            code, body, ctype = _json({"instances": items})
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path == "/api/creds":
            creds=_load_creds()
            # hide token partially for display? but editable so send full
            code, body, ctype = _json({"creds": creds})
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path == "/api/config":
            out={}
            for name in ALLOWED_CONFIG:
                p=CONFIG_DIR / name
                out[name]=p.read_text(encoding="utf-8") if p.exists() else ""
            # also include creds.json raw for settings
            code, body, ctype = _json({"config": out})
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path == "/api/memory":
            try:
                from src.action.memory import load_memory, ensure_memory
                ensure_memory()
                mem=load_memory(max_chars=8000)
                code, body, ctype = _json({"memory": mem})
            except Exception as e:
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path == "/api/logs":
            # Phase 7 — run log: /api/logs?limit=50[&task=x][&job_id=y][&summary=1]
            qs = urllib.parse.parse_qs(parsed.query)
            try:
                from src.action import logbook
                def _int(key, default):
                    try: return int(qs.get(key, [default])[0])
                    except (TypeError, ValueError): return default
                if qs.get("summary"):
                    code, body, ctype = _json({"summary": logbook.summary(limit=_int("limit", 200))})
                else:
                    entries = logbook.read(
                        limit=_int("limit", 50),
                        task=(qs.get("task", [""])[0] or None),
                        job_id=(qs.get("job_id", [""])[0] or None),
                    )
                    # summary always covers SUMMARY_WINDOW entries, independent of page limit,
                    # so the RUNS panel header reflects the whole recent window
                    code, body, ctype = _json({
                        "runs": entries,
                        "summary": logbook.summary(limit=int(os.getenv("BANANA_LOG_SUMMARY_WINDOW", "200"))),
                    })
            except Exception as e:
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path == "/api/jobs":
            # Phase 10 — all jobs grouped by kind + scheduler health
            try:
                from src.scheduler import registry, daemon
                from src.scheduler.jobs import preview
                grouped = registry.grouped()
                for kind_jobs in grouped.values():
                    for j in kind_jobs:
                        j.update(preview(j))
                code, body, ctype = _json({"jobs": grouped, "scheduler": daemon.status()})
            except Exception as e:
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path.startswith("/api/jobs/"):
            rest = path[len("/api/jobs/"):].split("?")[0].strip("/")
            parts = [p for p in rest.split("/") if p]
            if not parts:
                self.send_error(400, "job id required"); return
            job_id, action = parts[0], (parts[1] if len(parts) > 1 else "")
            try:
                from src.scheduler import registry
                job = registry.get(job_id)
                if not job:
                    code, body, ctype = _json({"error": f"no job {job_id}"}, 404)
                elif action == "runs":
                    # job_run_id is "{job_id}:{ts}" so runs are matched by prefix
                    from src.action import logbook
                    qs = urllib.parse.parse_qs(parsed.query)
                    try:
                        lim = int(qs.get("limit", ["20"])[0])
                    except (TypeError, ValueError):
                        lim = 20
                    runs = [e for e in logbook.read(limit=500)
                            if (e.get("job_id") or "").startswith(job_id + ":")]
                    code, body, ctype = _json({"job_id": job_id, "runs": runs[:lim]})
                else:
                    code, body, ctype = _json({"job": job})
            except Exception as e:
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path == "/api/chats":
            try:
                from src.action.chats import list_chats
                code, body, ctype = _json({"chats": list_chats()})
            except Exception as e:
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path.startswith("/api/chats/"):
            # GET /api/chats/{id}
            chat_id = path[len("/api/chats/"):].split("?")[0].split("/")[0].strip()
            if not chat_id:
                code, body, ctype = _json({"error": "chat_id required"}, 400)
                self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
            try:
                from src.action.chats import get_chat
                chat=get_chat(chat_id)
                if not chat:
                    code, body, ctype = _json({"error": "chat not found"}, 404)
                else:
                    code, body, ctype = _json({"chat": chat})
            except Exception as e:
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path.startswith("/static/"):
            f = STATIC / path[len("/static/"):]
            if f.exists() and f.is_file():
                self.send_response(200)
                mime="text/plain"
                if f.suffix==".css": mime="text/css"
                elif f.suffix==".js": mime="application/javascript"
                elif f.suffix==".html": mime="text/html"
                elif f.suffix==".json": mime="application/json"
                self.send_header("Content-Type", mime); self.end_headers(); self.wfile.write(f.read_bytes()); return
        self.send_error(404, f"not found {path}")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try: data = json.loads(raw.decode()) if raw else {}
        except: data = {}
        if path == "/api/chat":
            msg = data.get("message") or data.get("text") or ""
            mock = bool(data.get("mock"))
            chat_id = data.get("chat_id") or data.get("chatId") or ""
            # also allow query param ?chat_id=
            qs=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if not chat_id and qs.get("chat_id"):
                chat_id=qs["chat_id"][0]
            if not msg.strip():
                code, body, ctype = _json({"error":"message required"}, 400)
                self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
            try:
                from src.main import _run_once
                from src.detector.detector import from_message
                from src.action.chats import ensure_chat
                # ensure chat exists, create if not provided
                if not chat_id:
                    # create new chat lazily
                    ch=ensure_chat(None)
                    chat_id=ch["id"]
                else:
                    # ensure exists
                    ch=ensure_chat(chat_id)
                    chat_id=ch["id"]
                given = from_message(msg, source="gui", meta_extra={"chat_id": chat_id})
                out = _run_once(given, mock=mock)
                resp = {
                    "given": out["given"],
                    "task": out["result"].get("task"),
                    "output": out["result"].get("output"),
                    "status": out["result"].get("status"),
                    "error": out["result"].get("error"),
                    "error_kind": out["result"].get("error_kind",""),
                    "attempts": out["result"].get("attempts",1),
                    "instance": out["instance"],
                    "cli_raw": out["result"].get("cli_raw","")[:4000],
                    "chat_text": out["result"].get("chat_text","")[:2000],
                    "created_tasks": out["result"].get("created_tasks",[]),
                    "job": out["result"].get("job"),
                    "steps": [
                        {"step": s.get("step"), "task": s.get("task"), "status": s.get("status"),
                         "error_kind": s.get("error_kind"), "attempts": s.get("attempts"),
                         "output": (s.get("output") or "")[:500]}
                        for s in (out["result"].get("steps") or [])
                    ],
                    "chat_id": chat_id,
                }
                code, body, ctype = _json(resp)
            except Exception as e:
                import traceback; traceback.print_exc()
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(body); return
        if path == "/api/jobs":
            # Phase 10 — POST /api/jobs {id,kind,schedule,task,args,...}
            try:
                from src.scheduler import registry
                job = registry.create(data)
                code, body, ctype = _json({"ok": True, "job": job}, 201)
            except ValueError as e:
                code, body, ctype = _json({"error": str(e)}, 400)
            except Exception as e:
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(body); return
        if path.startswith("/api/jobs/"):
            # POST /api/jobs/{id}/run  |  POST /api/jobs/{id}/toggle
            rest = path[len("/api/jobs/"):].split("?")[0].strip("/")
            parts = [p for p in rest.split("/") if p]
            job_id, action = (parts + ["", ""])[:2]
            if not action:
                code, body, ctype = _json({"error": "action required (run|toggle)"}, 400)
                self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
            try:
                from src.scheduler import registry
                if action == "toggle":
                    job = registry.toggle(job_id, data.get("enabled"))
                    if not job:
                        code, body, ctype = _json({"error": f"no job {job_id}"}, 404)
                    else:
                        code, body, ctype = _json({"ok": True, "job": job})
                elif action == "run":
                    job = registry.get(job_id)
                    if not job:
                        code, body, ctype = _json({"error": f"no job {job_id}"}, 404)
                    else:
                        from src.scheduler.jobs import execute_job
                        from src.scheduler import registry as _reg
                        res = execute_job(job)
                        try:
                            _reg.mark_run(job_id)
                        except Exception:
                            pass
                        code, body, ctype = _json({
                            "ok": res.get("status") == "ok",
                            "result": {k: res.get(k) for k in
                                       ("status", "task", "output", "error", "error_kind",
                                        "exit_code", "attempts", "job_run_id", "instance")},
                        })
                else:
                    code, body, ctype = _json({"error": f"unknown action {action}"}, 400)
            except Exception as e:
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(body); return
        if path == "/api/chats":
            # POST /api/chats {title} -> create chat
            title = data.get("title") or data.get("name") or ""
            try:
                from src.action.chats import create_chat
                chat=create_chat(title=title)
                code, body, ctype = _json({"ok": True, "chat": chat})
            except Exception as e:
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path.startswith("/api/chats/"):
            # POST /api/chats/{id} for rename, or DELETE handled via do_DELETE but also support POST with _method
            chat_id = path[len("/api/chats/"):].split("?")[0].split("/")[0].strip()
            # if method is POST and data contains _delete or action delete
            if data.get("_delete") or data.get("action")=="delete":
                try:
                    from src.action.chats import delete_chat
                    ok=delete_chat(chat_id)
                    code, body, ctype = _json({"ok": ok})
                except Exception as e:
                    code, body, ctype = _json({"error": str(e)}, 500)
                self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
            # rename
            if data.get("title") or data.get("name"):
                try:
                    from src.action.chats import rename_chat
                    chat=rename_chat(chat_id, data.get("title") or data.get("name"))
                    if not chat:
                        code, body, ctype = _json({"error":"chat not found"},404)
                    else:
                        code, body, ctype = _json({"ok": True, "chat": chat})
                except Exception as e:
                    code, body, ctype = _json({"error": str(e)}, 500)
                self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
            code, body, ctype = _json({"error":"missing title or action"},400)
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path == "/api/creds":
            # data is creds dict or {creds:{...}}
            updates = data.get("creds") if isinstance(data.get("creds"), dict) else data
            if not isinstance(updates, dict):
                code, body, ctype = _json({"error":"creds must be object"}, 400)
                self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
            try:
                from src.creds import save_creds, load_creds
                new=save_creds(updates)
                code, body, ctype = _json({"ok":True,"creds":new})
            except Exception as e:
                code, body, ctype = _json({"error":str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path == "/api/config":
            fname = data.get("file") or data.get("name")
            content = data.get("content", "")
            if not fname or fname not in ALLOWED_CONFIG:
                code, body, ctype = _json({"error": f"file must be one of {sorted(ALLOWED_CONFIG)}"}, 400)
                self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
            try:
                p=CONFIG_DIR / fname
                p.write_text(content, encoding="utf-8")
                code, body, ctype = _json({"ok":True,"file":fname})
            except Exception as e:
                code, body, ctype = _json({"error":str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        if path == "/api/memory":
            content=data.get("content") or data.get("memory") or ""
            if not content and not data.get("content"):
                code, body, ctype = _json({"error":"content required"},400)
                self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
            try:
                from src.action.memory import _mem_path
                p=_mem_path()
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
                code, body, ctype = _json({"ok":True})
            except Exception as e:
                code, body, ctype = _json({"error":str(e)},500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        self.send_error(404, f"not found {path}")

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/jobs/"):
            job_id = path[len("/api/jobs/"):].split("?")[0].strip("/")
            try:
                from src.scheduler import registry
                ok = registry.delete(job_id)
                code, body, ctype = _json({"ok": ok} if ok else {"error": f"no job {job_id}"}, 200 if ok else 404)
            except Exception as e:
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(body); return
        if path.startswith("/api/chats/"):
            chat_id = path[len("/api/chats/"):].split("?")[0].split("/")[0].strip()
            try:
                from src.action.chats import delete_chat
                ok=delete_chat(chat_id)
                code, body, ctype = _json({"ok": ok})
            except Exception as e:
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(body); return
        self.send_error(404, f"not found {path}")

    def do_PUT(self):
        # used for rename chat: PUT /api/chats/{id} {title}
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try: data = json.loads(raw.decode()) if raw else {}
        except: data={}
        if path.startswith("/api/jobs/"):
            # PUT /api/jobs/{id} — partial update
            job_id = path[len("/api/jobs/"):].split("?")[0].strip("/")
            changes = data.get("job") if isinstance(data.get("job"), dict) else data
            try:
                from src.scheduler import registry
                job = registry.update(job_id, changes)
                if not job:
                    code, body, ctype = _json({"error": f"no job {job_id}"}, 404)
                else:
                    code, body, ctype = _json({"ok": True, "job": job})
            except ValueError as e:
                code, body, ctype = _json({"error": str(e)}, 400)
            except Exception as e:
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(body); return
        if path.startswith("/api/chats/"):
            chat_id = path[len("/api/chats/"):].split("?")[0].split("/")[0].strip()
            title=data.get("title") or data.get("name") or ""
            if not title:
                code, body, ctype = _json({"error":"title required"},400)
                self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
            try:
                from src.action.chats import rename_chat
                chat=rename_chat(chat_id, title)
                if not chat:
                    code, body, ctype = _json({"error":"chat not found"},404)
                else:
                    code, body, ctype = _json({"ok":True,"chat":chat})
            except Exception as e:
                code, body, ctype = _json({"error":str(e)},500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
        self.send_error(404, f"not found {path}")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

def run(host="127.0.0.1", port=4242):
    addr = (host, port)
    httpd = HTTPServer(addr, Handler)
    print(f"Banana Web GUI (React, black/white) at http://{host}:{port}", flush=True)
    print(f"Static: {STATIC}/index.html  API: /api/chat /api/creds /api/config", flush=True)
    try: httpd.serve_forever()
    except KeyboardInterrupt: print("stopped"); httpd.server_close()

if __name__ == "__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4242)
    args=p.parse_args()
    run(args.host, args.port)
