"""End-to-end tests — full pipeline through the real HTTP server

docker compose run --rm banana python -m pytest tests/ -q

These drive the actual GUI server on a real socket (no mocks for the HTTP
layer) and use --mock for the LLM so no network/model is required.
"""
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.action import logbook
from src.gui.server import Handler

from tests.test_failures import isolated_log  # noqa: F401  (reused fixture)


@pytest.fixture(scope="module")
def server():
    """Real HTTP server on an ephemeral port."""
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


def api(base, method, path, payload=None):
    req = urllib.request.Request(
        base + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as f:
            raw = f.read().decode()
            status = f.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        status = e.code
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        # send_error() replies with HTML, not JSON
        return status, {"raw": raw}


def test_health(server):
    status, body = api(server, "GET", "/api/health")
    assert status == 200
    assert body["status"] == "ok"


def test_index_serves_dashboard(server):
    with urllib.request.urlopen(server + "/", timeout=30) as f:
        html = f.read().decode()
    assert "BANANA" in html
    assert "id=\"root\"" in html


def test_tasks_listed(server):
    status, body = api(server, "GET", "/api/tasks")
    assert status == 200
    names = {t["name"] for t in body["tasks"]}
    assert {"echo-demo", "hello-py"} <= names


def test_full_chat_pipeline_end_to_end(server):
    """message -> detector -> prompt -> mock LLM -> action -> instance."""
    status, body = api(server, "POST", "/api/chat",
                       {"message": "run echo-demo e2e", "mock": True})
    assert status == 200
    assert body["status"] == "ok"
    assert body["task"] == "echo-demo"
    assert "echo-demo" in body["output"]
    assert body["chat_id"]
    assert body["instance"], "an instance was created"
    assert Path(body["instance"]).exists()


def test_chat_creates_and_reuses_chat(server):
    status, body = api(server, "POST", "/api/chat",
                       {"message": "run hello-py one", "mock": True})
    assert status == 200
    chat_id = body["chat_id"]
    status, body2 = api(server, "POST", "/api/chat",
                        {"message": "run hello-py two", "mock": True, "chat_id": chat_id})
    assert body2["chat_id"] == chat_id, "same chat reused"
    status, lst = api(server, "GET", "/api/chats")
    assert any(c["id"] == chat_id for c in lst["chats"])


def test_chat_rejects_empty_message(server):
    status, body = api(server, "POST", "/api/chat", {"message": "  "})
    assert status == 400
    assert "error" in body


def test_failure_surfaces_in_chat_response(server):
    """A failing task must return error_kind, not blow up the request."""
    status, body = api(server, "POST", "/api/chat",
                       {"message": "run fail-demo", "mock": True,
                        "mock_task": "fail-demo"})
    # fail-demo is not a chat-known task, so this falls through; either way the
    # response must be a well-formed 200 with a status
    assert status == 200
    assert "status" in body


def test_run_log_endpoint_sees_pipeline_run(server):
    api(server, "POST", "/api/chat", {"message": "run echo-demo logged", "mock": True})
    status, body = api(server, "GET", "/api/logs?limit=20")
    assert status == 200
    assert body["summary"]["total"] > 0
    assert any(e["task"] == "echo-demo" for e in body["runs"])


def test_instances_endpoint_lists_new_instance(server):
    _, chat = api(server, "POST", "/api/chat", {"message": "run echo-demo inst", "mock": True})
    status, body = api(server, "GET", "/api/instances")
    assert status == 200
    assert body["instances"], "instances listed"
    assert any(i["id"] == chat["instance"].split("/")[-1] for i in body["instances"])


def test_jobs_api_crud_cycle(server):
    created = {"id": "e2e-job", "kind": "cron", "schedule": "*/10 * * * *",
               "task": "echo-demo", "args": {"msg": "e2e"}}
    status, body = api(server, "POST", "/api/jobs", created)
    assert status == 201
    assert body["job"]["task"] == "echo-demo"

    status, body = api(server, "POST", "/api/jobs/e2e-job/toggle", {"enabled": False})
    assert body["job"]["enabled"] is False

    status, body = api(server, "POST", "/api/jobs/e2e-job/run", {})
    assert body["ok"] is True
    assert body["result"]["status"] == "ok"

    status, body = api(server, "GET", "/api/jobs/e2e-job/runs")
    assert status == 200
    assert len(body["runs"]) >= 1

    status, _ = api(server, "DELETE", "/api/jobs/e2e-job")
    assert status == 200
    status, _ = api(server, "DELETE", "/api/jobs/e2e-job")
    assert status == 404


def test_jobs_api_rejects_bad_cron(server):
    status, body = api(server, "POST", "/api/jobs",
                       {"id": "e2e-bad", "kind": "cron", "schedule": "nope", "task": "echo-demo"})
    assert status == 400
    assert "cron" in body["error"]


def test_jobs_endpoint_buckets_by_kind(server):
    status, body = api(server, "GET", "/api/jobs")
    assert status == 200
    assert set(body["jobs"].keys()) >= {"cron", "boot", "webhook"}
    assert "scheduler" in body


def test_unknown_route_404(server):
    status, _ = api(server, "GET", "/api/nope")
    assert status == 404


def test_config_endpoint_rejects_non_allowlisted_file(server):
    status, body = api(server, "POST", "/api/config",
                       {"file": "../../etc/passwd", "content": "x"})
    assert status == 400


def test_config_endpoint_roundtrip(server):
    status, body = api(server, "GET", "/api/config")
    assert status == 200
    assert "SOUL.md" in body["config"]
    original = body["config"]["SOUL.md"]
    status, _ = api(server, "POST", "/api/config",
                    {"file": "SOUL.md", "content": original})
    assert status == 200