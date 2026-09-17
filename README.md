# Banana Bot

> **Give Banana a job and let it get the job done.** — Minimal personal automation, not OpenClaw. See `plan.md:3-13`.

Containerized, file-based, opencode-native. Whole thing runs **inside Docker** `plan.md:247`.

## Architecture

```
Message / CRON -> Detector -> Prompt (Given+Context+System) -> CLI Code (opencode) -> ACTION -> /TASKS <-> /INSTANCES
```
`opencode` IS the LLM adapter — no separate provider `plan.md:32,100`.

## Project Structure

```
.
├── Dockerfile            # python:3.11-slim + node + bash, opencode 1.18.31
├── docker-compose.yml    # service banana, volumes tasks/instances/config/src
├── requirements.txt      # croniter, python-dateutil
├── plan.md / AGENTS.md / WORKFLOW.md
├── config/               # System prompts
│   ├── SOUL.md AGENT.md USER.md ENTRY.md SKILL.md
├── src/
│   ├── detector/         # triggers -> Given
│   ├── prompt/           # Given+Context+System -> prompt
│   ├── cli/              # opencode wrapper (LLM adapter)
│   └── action/           # task executor + instances + reaper
├── tasks/
│   ├── echo-demo/        # bash demo
│   └── hello-py/         # python demo
└── instances/
    ├── temp/             # TTL 72h, auto-reaped
    └── permanent/        # persist until deleted
```

## Quick Start

```bash
cp .env.example .env  # add opencode auth: OPENCODE_MODEL, etc.
sudo docker compose build
sudo docker compose run --rm banana echo "ok"  # verify
```

If you did `sudo usermod -aG docker $USER`, relogin or prefix with `sudo docker ...` until then.

## Pipeline

### 1. Detector — `src/detector/`

Normalized `Given` `{id, source, timestamp, text, meta}` `WORKFLOW.md:32`.

```bash
sudo docker compose run --rm banana python -m src.detector --message "run echo-demo hello"
sudo docker compose run --rm banana python -m src.detector --message "hi" --source telegram
sudo docker compose run --rm banana python -m src.detector --cron "*/5 * * * *" --task echo-demo
```

Schema: `src/detector/schema.json`. Impl: `detector.py:from_message`, `from_cron` (croniter).

### 2. Prompt — `src/prompt/`

`Given + Context + System -> prompt.md` `plan.md:67-96`.

- `load_system()` reads `config/SOUL.md` etc., dedupes `SKILL.md`
- `load_context()` includes `instances/permanent/*` + hinted `tasks/{name}/README.md`
- Truncates to 4k tokens (~16k chars) `builder.py:14`

```bash
sudo docker compose run --rm banana python -m src.prompt --message "run echo-demo hello" | head -n 50
```

### 3. CLI (opencode) — `src/cli/`

Wrapper for `opencode 1.18.31` `plan.md:100`.

- `opencode run --format json <prompt>` (verified CLI)
- Parses `TASK: <name>` + `ARGS: {...}` or JSON, validates `tasks/<name>` exists
- `run(prompt, timeout=120, retry=1)` — mock mode `MOCK_OPENCODE=1` for tests without auth
- Auth via `opencode.json` / `.env`, never hardcoded

```bash
sudo docker compose run --rm banana opencode --version
sudo docker compose run --rm banana python -m src.cli --prompt "hello" --mock
sudo docker compose run --rm banana python -m src.cli --prompt "hello" --mock --json
```

### 4. Action — `src/action/`

Executes `tasks/{name}/run.sh` or `run.py` `WORKFLOW.md:76`.

```bash
sudo docker compose run --rm banana python -m src.action --task echo-demo --args '{"msg":"hello"}'
sudo docker compose run --rm banana python -m src.action --task hello-py --args '{"msg":"hello"}'
sudo docker compose run --rm banana python -m src.action --task echo-demo --args "hi" --temp  # also creates instance
```

**Instances:** `instances.py` — `create_temp(given,result)` -> `instances/temp/{uuid}/context.json` (`created_at`, `keep`, `TASKS`), `create_permanent(id,...)`. Reaper `reaper.py` deletes `temp` older than 72h unless `keep:true` `plan.md:137`.

```bash
sudo docker compose run --rm banana python -m src.action.reaper --dry-run
sudo docker compose run --rm banana python -m src.action.reaper  # actually reap
```

**Tasks:** Each `tasks/{name}/` needs `run.sh` or `run.py` + `README.md` (inputs/outputs) `AGENTS.md:82`. Writes confined to `/app/instances` + `/app/tasks`.

## Tasks

| Task | Run | Input | Output |
|------|-----|-------|--------|
| `echo-demo` | `bash tasks/echo-demo/run.sh` | `msg` string or JSON | `echo-demo: <msg>` |
| `hello-py` | `python tasks/hello-py/run.py` | `msg` | `hello-py: <msg> — from python task` |

Add new: `mkdir tasks/my-task && echo '#...' > README.md && cat > run.sh` + `chmod +x`.

## Instances

- `instances/temp/{uuid}/context.json` + `TASKS` — auto-expire 72h
- `instances/permanent/{id}/` — manual delete
- Mounted via `docker-compose.yml:6-8`, file-based no DB `AGENTS.md:72`.

## Config

`config/*.md` are system prompts `AGENTS.md:81`. Agents read, don't overwrite without approval. `ENTRY.md` defines `TASK:` contract for opencode.

## Status

Phases `WORKFLOW.md`:

- [x] Phase 0 — Container bootstrap (Dockerfile, compose, 150s build)
- [x] Phase 1 — Detector (gui/telegram/cron -> Given)
- [x] Phase 2 — Prompt builder (System+Context+Given, 4k token cap)
- [x] Phase 3 — opencode wrapper (1.18.31, mock + timeout)
- [x] Phase 4 — Action executor + instances + demo tasks
- [ ] Phase 5 — Glue `src/main.py` (detector->prompt->cli->action->instance)
- [ ] Phase 6 — Telegram/GUI polish

Current: Phase 4 done `2026-09-17`. Next: Phase 5 glue.

## MVP Checklist `plan.md:253-260`

- [x] Receive message
- [x] Receive CRON
- [x] Detect/trigger task (Given)
- [x] Build prompt (Given+Context+System)
- [x] Use opencode CLI
- [x] Execute tasks
- [x] Store state in instances (temp/permanent, 72h)
- [ ] Return result via main pipeline (Phase 5)

## Principles `plan.md:228-237`

Minimalism, job first, use existing tools, file-based state, executable tasks, don't build OpenClaw, containerized.

## License

Personal project. No license yet.
