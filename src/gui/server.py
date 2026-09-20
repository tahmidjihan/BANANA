"""Web GUI server — ChatGPT-like, stdlib only (no Flask)
GET / -> static/index.html
POST /api/chat {message, mock} -> pipeline (detector->prompt->cli->action->instance)
GET /api/tasks, /api/instances, /api/health
Run host:  /tmp/banana-venv/bin/python -m src.gui.server --port 8080
Run docker: sudo docker compose run --rm -p 8080:8080 banana python -m src.gui.server --host 0.0.0.0 --port 8080
"""
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).parent / "static"

def _json(data, code=200):
    body = json.dumps(data, ensure_ascii=False).encode()
    return code, body, "application/json"

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # quiet except errors
        print(f"{self.client_address[0]} {format%args}", flush=True)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/" or path == "/index.html":
            f = STATIC / "index.html"
            if not f.exists():
                self.send_error(404, "index.html not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f.read_bytes())
            return
        if path == "/api/health":
            code, body, ctype = _json({"status":"ok","model": os.getenv("OPENCODE_MODEL","opencode/big-pickle")})
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/tasks":
            tasks_dir = ROOT / "tasks"
            tasks = []
            if tasks_dir.exists():
                for d in sorted(tasks_dir.iterdir()):
                    if d.is_dir() and not d.name.startswith("."):
                        readme = (d / "README.md").read_text()[:200] if (d / "README.md").exists() else ""
                        tasks.append({"name": d.name, "readme": readme})
            code, body, ctype = _json({"tasks": tasks})
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/instances":
            base = ROOT / "instances" / "temp"
            items = []
            if base.exists():
                for p in sorted(base.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
                    if p.is_dir() and (p / "context.json").exists():
                        try:
                            data = json.loads((p / "context.json").read_text())
                            items.append({"id": p.name, "given": data.get("given"), "result": data.get("result"), "created_at": data.get("created_at")})
                        except Exception:
                            pass
            code, body, ctype = _json({"instances": items})
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)
            return
        # static files
        if path.startswith("/static/"):
            f = STATIC / path[len("/static/"):]
            if f.exists() and f.is_file():
                self.send_response(200)
                # minimal mime
                mime = "text/plain"
                if f.suffix == ".css": mime = "text/css"
                elif f.suffix == ".js": mime = "application/javascript"
                self.send_header("Content-Type", mime)
                self.end_headers()
                self.wfile.write(f.read_bytes())
                return
        self.send_error(404, f"not found {path}")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode()) if raw else {}
        except Exception:
            data = {}
        if path == "/api/chat":
            msg = data.get("message") or data.get("text") or ""
            mock = bool(data.get("mock"))
            # default to mock if no model configured? but now big-pickle is set, use real by default
            # allow ?mock=1 query or mock flag
            if not msg.strip():
                code, body, ctype = _json({"error":"message required"}, 400)
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.end_headers()
                self.wfile.write(body)
                return
            try:
                from src.main import _run_once
                from src.detector.detector import from_message
                given = from_message(msg, source="gui")
                out = _run_once(given, mock=mock)
                # shape for chat UI
                # status chat -> just return opencode chat output, no error
                # output is clean decoded text; cli_raw is full trace for expand
                resp = {
                    "given": out["given"],
                    "task": out["result"].get("task"),
                    "output": out["result"].get("output"),
                    "status": out["result"].get("status"),
                    "error": out["result"].get("error"),
                    "instance": out["instance"],
                    "cli_raw": out["result"].get("cli_raw","")[:4000],
                    "chat_text": out["result"].get("chat_text","")[:2000],
                }
                code, body, ctype = _json(resp)
            except Exception as e:
                import traceback
                traceback.print_exc()
                code, body, ctype = _json({"error": str(e)}, 500)
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return
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
    print(f"Banana Web GUI at http://{host}:{port}  (ChatGPT-like)", flush=True)
    print(f"Static: {STATIC}/index.html  API: /api/chat", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
        httpd.server_close()

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()
    run(args.host, args.port)
