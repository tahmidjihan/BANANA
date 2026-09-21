# BANANA

> **Give Banana a job and let it get the job done.** — Minimal personal automation, not OpenClaw. See `plan.md:3-13`.

Containerized, file-based, opencode-native. Whole thing runs **inside one Docker container** `plan.md:247` — plug-and-play anywhere. Port **`31415` = π `3.1415…`** — not `8080`, not lame, irrational like Banana, memorable.

## Architecture

```
Message / CRON -> Detector -> Prompt (Given+Context+System+Chat) -> CLI Code (opencode) -> ACTION -> /TASKS <-> /INSTANCES (/chats)
```
`opencode` IS the LLM adapter — no separate provider `plan.md:32,100`. Free `opencode/big-pickle` via `opencode --auto` (no API key), or swap `OPENCODE_MODEL` in `config/creds.json`.

## Project Structure

```
.
├── Dockerfile            # python:3.11-slim + node+git+jq, opencode 1.18.31, PORT 31415
├── docker-compose.yml    # single service banana, 31415:31415, volumes optional, healthcheck
├── docker-entrypoint.sh  # plug-and-play — GUI 0.0.0.0:31415 + Telegram polling in ONE container
├── start.sh              # host mode — now 31415 default (π), --port/--telegram/--mock/--docker
├── requirements.txt      # croniter, python-dateutil, requests
├── plan.md / AGENTS.md / WORKFLOW.md
├── config/
│   ├── creds.json        # JSON creds — OPENCODE_MODEL, TELEGRAM_BOT_TOKEN, editable via UI ⚙ or chat
│   ├── creds.example.json
│   ├── SOUL.md AGENT.md USER.md ENTRY.md SKILL.md  # self-editable prompts (agent can write)
│   └── schedule.json     # file-based schedule (daily-news 05:00 Dhaka)
├── src/
│   ├── creds.py          # loader — env > creds.json > .env
│   ├── detector/         # triggers -> Given {id,source,timestamp,text,meta:{chat_id}}
│   ├── prompt/           # Given+Context+System+ChatHistory -> prompt (4k cap)
│   ├── cli/              # opencode wrapper --auto --format json, TASK parse, chat fallback
│   ├── action/           # executor + instances + chats + reaper
│   │   ├── chats.py      # chats file-based, agent aware
│   │   └── reaper.py
│   ├── gui/              # React brutal minimalist — black #000 white #fff 2px borders, markdown, /brutal-minimalist-design
│   └── tui/              # REPL
├── tasks/
│   ├── echo-demo/ reverse-text/ title-case/ count-words/ hello-py/ daily-news/
└── instances/
    ├── temp/             # TTL 72h auto-reaped
    ├── chats/            # chats/{id}/chat.json — permanent until deleted, agent aware
    ├── permanent/        # persist until deleted
    └── logs/
```

## Quick Start — Plug-and-Play Single Container

**1. Install Docker systemwide (Fedora 44 — needs password prompt):**
```bash
sudo dnf install -y moby-engine docker-cli docker-compose docker-buildx
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker  # or logout/login
docker --version && docker compose version
# alternative shim: sudo dnf install -y podman-docker  # docker CLI via podman
```

**2. Creds — `config/creds.json` (editable via UI ⚙ or `write`):**
```json
{
  "OPENCODE_MODEL": "opencode/big-pickle",
  "TELEGRAM_BOT_TOKEN": "from @BotFather",
  "TELEGRAM_ALLOWED_CHAT_ID": "",
  "OLLAMA_HOST": "http://host.docker.internal:11434"
}
```
Fallback: `.env` → `config/creds.json` → `env var`.

**3. Run — one container does everything (GUI + Telegram):**
```bash
docker compose up --build -d   # → http://localhost:31415 + /brutal-minimalist-design  (BANANA-BOT)
# or
docker build -t banana . && docker run -d -p 31415:31415 -v ./config/creds.json:/app/config/creds.json banana
# host mode still:
./start.sh                     # 31415 default (π)
./start.sh --telegram --port 31415
curl http://localhost:31415/api/health
```

No volumes needed — ephemeral works. Add volumes in `docker-compose.yml` for persistence (`./instances`, `./config/creds.json`, `./tasks`).

## Dashboard — Brutal Minimalist

`/` and `/brutal-minimalist-design` → **BANANA-BOT** React `src/gui/static/index.html:1`:
* Black `#000` bg white `#fff` text, **2px solid** outer borders, **1px #232323 gray** inner — symmetrical `14px 16px`, `0 radius`, `ui-monospace`, uppercase brutal.
* Markdown via `marked`, **trace ›** expandable `cli_raw`, subtle `brutalBlink` dashed + squares `brutalPulse` when generating.
* Sidebar: **CHATS** `+ NEW`, `TASKS`, `INSTANCES`, `MODEL`; `⚙` settings.

## Pipeline

### 1. Detector — `src/detector/`
`Given {id, source, timestamp, text, meta:{chat_id}}` `WORKFLOW.md:32`.
```bash
docker compose run --rm banana python -m src.detector --message "run echo-demo hello"
python -m src.detector --message "hi" --source telegram
```

### 2. Prompt — `src/prompt/`
`Given + Context + System + ChatHistory -> prompt.md` `plan.md:67-96`.
* `load_system()` `config/SOUL.md` etc.
* `load_context()` `instances/permanent/*` + hinted `tasks/{name}/README.md` + **Current Chat History** last 12 turns if `meta.chat_id` `builder.py:11`.
* 4k tokens cap `builder.py:14`.

### 3. CLI (opencode) — `src/cli/`
`opencode run --format json --auto <prompt>` `plan.md:100`.
* Parses `TASK: <name>` + `ARGS: {...}` or JSON, validates `tasks/<name>`.
* `run(prompt, timeout=120, retry=1)` — `chat_text` fallback for `hi`, `MOCK_OPENCODE=1`.
* Model via `OPENCODE_MODEL` from `config/creds.json`.

### 4. Action — `src/action/`
`tasks/{name}/run.sh|run.py` `WORKFLOW.md:76`.
```bash
python -m src.action --task echo-demo --args '{"msg":"hello"}'
python -m src.main --message "run echo-demo hello" --json
```
**Chats:** `chats.py` file-based `instances/chats/{id}/chat.json` — `create/list/get/delete/rename/add`, agent aware, `instances/chats/.gitkeep`, `builder.py:11` history. UI creates/deletes, agent does `write instances/chats/{id}/chat.json` / `rm -rf`.
**Instances:** `create_temp` → `instances/temp/{uuid}/context.json` + `TASKS`, `create_permanent`, `reaper.py` 72h.

## Tasks

| Task | Run | Input | Output |
|------|-----|-------|--------|
| `echo-demo` | `bash tasks/echo-demo/run.sh` | `msg` JSON | `echo-demo: <msg>` |
| `hello-py` | `python tasks/hello-py/run.py` | `msg` | `hello-py: <msg> — from python` |
| `count-words` | `tasks/count-words/run.sh` | `msg` | word count |
| `reverse-text` | `tasks/reverse-text/run.sh` | `msg` | reversed |
| `title-case` | `tasks/title-case/run.sh` | `msg` | Title Case |
| `daily-news` | `python tasks/daily-news/run.py` | `dry_run, chat_id, categories, limit` | tech/science/politics → Telegram 05:00 Dhaka `config/schedule.json` |

Add: `mkdir tasks/my-task && echo '#...' > README.md && cat > run.sh && chmod +x run.sh` — agent can do same via `write` when you say `create task ...`.

## Instances & Chats

* `instances/temp/{uuid}/context.json` + `TASKS` — auto-expire 72h
* `instances/chats/{id}/chat.json` — `{id,title,created_at,updated_at,messages:[{role,text,timestamp}]}` — permanent until deleted, agent aware
* `instances/permanent/{id}/` — manual delete
* Via `docker-compose.yml` volumes, file-based no DB `AGENTS.md:72`.

```bash
curl http://localhost:31415/api/chats | jq
curl -X POST http://localhost:31415/api/chats -H 'Content-Type: application/json' -d '{"title":"My Chat"}' | jq
curl http://localhost:31415/api/chats/{id} | jq
curl -X DELETE http://localhost:31415/api/chats/{id}
curl -X POST http://localhost:31415/api/chat -H 'Content-Type: application/json' -d '{"message":"hi","chat_id":"{id}"}' | jq
```

## Config — Self-Editable

`config/*.md` `AGENTS.md:81` + `config/creds.json` — **agent edits itself** on ask (`ENTRY.md:5`): `read config/SOUL.md` → `write config/SOUL.md`, `write tasks/...`, `write src/...`, `write instances/chats/...` with `--auto`. UI `⚙` edits same files (`GET/POST /api/creds`, `/api/config`).

## Status

* [x] Phase 0 — Container bootstrap (Dockerfile 31415, healthcheck)
* [x] Phase 1 — Detector (gui/telegram/cron)
* [x] Phase 2 — Prompt builder (System+Context+Given+Chat, 4k cap)
* [x] Phase 3 — opencode wrapper (1.18.31, v2 JSONL decode, --auto)
* [x] Phase 4 — Action + chats + demo tasks
* [x] Phase 5 — Glue `src/main.py` chat-aware, created-tasks detect
* [x] Phase 6 — Telegram/GUI brutal React, markdown, settings, chats

Current: **Brutal minimalist** `BANANA-BOT` at `31415` (`/` + `/brutal-minimalist-design`), chats agent-aware, self-edit, single-container plug-and-play `8153e24`.

## MVP Checklist `plan.md:253-260`

* [x] Receive message / CRON
* [x] Detect/trigger task (Given)
* [x] Build prompt (Given+Context+System+Chat)
* [x] Use opencode CLI
* [x] Execute tasks
* [x] Store state in instances (temp/chats/permanent, 72h)
* [x] Return result via main pipeline + GUI markdown + trace

## Principles `plan.md:228-237`

Minimalism, job first, use existing tools, file-based state, executable tasks, don't build OpenClaw, containerized — now **brutal black/white 2px borders, 0 radius, monospace, symmetrical, gray-balanced codeblocks**.

## License

Personal project. No license yet.
