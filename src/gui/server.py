"""Banana Web GUI server — React + Markdown, black/white minimalist
GET / -> static/index.html (React)
POST /api/chat {message, mock} -> pipeline
GET /api/tasks, /api/instances, /api/health, /api/creds, /api/config
POST /api/creds, /api/config
Run host: python -m src.gui.server --port 8080
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
                            items.append({"id":p.name,"given":data.get("given"),"result":data.get("result"),"created_at":data.get("created_at")})
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
            if not msg.strip():
                code, body, ctype = _json({"error":"message required"}, 400)
                self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body); return
            try:
                from src.main import _run_once
                from src.detector.detector import from_message
                given = from_message(msg, source="gui")
                out = _run_once(given, mock=mock)
                resp = {
                    "given": out["given"],
                    "task": out["result"].get("task"),
                    "output": out["result"].get("output"),
                    "status": out["result"].get("status"),
                    "error": out["result"].get("error"),
                    "instance": out["instance"],
                    "cli_raw": out["result"].get("cli_raw","")[:4000],
                    "chat_text": out["result"].get("chat_text","")[:2000],
                    "created_tasks": out["result"].get("created_tasks",[]),
                }
                code, body, ctype = _json(resp)
            except Exception as e:
                import traceback; traceback.print_exc()
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(body); return
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
        self.send_error(404, f"not found {path}")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

def run(host="127.0.0.1", port=8080):
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
    p.add_argument("--port", type=int, default=8080)
    args=p.parse_args()
    run(args.host, args.port)
