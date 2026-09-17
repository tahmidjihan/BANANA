# WORKFLOW.md — Execution Plan for Banana Bot

> How an agent (you) will execute `plan.md` step-by-step. One phase at a time. All inside Docker.

## 0. Overview

**Goal:** Minimal viable Banana that hits `plan.md:253-267` MVP.
**Constraint:** `plan.md:247-249` — Everything runs INSIDE docker container.
**Method:** Phased, vertical slices. No phase skipped. Each phase is build -> test in Docker -> mark done.

Status legend: `[ ] todo` `[~] in progress` `[x] done`

---

## Phase 0 — Repo & Container Bootstrap
**Goal:** Runnable empty container. No logic yet.

- [x] Create `Dockerfile` (python:3.11-slim + node + bash, workdir /app)
- [x] Create `docker-compose.yml` (service `banana`, volumes `./tasks:/app/tasks`, `./instances:/app/instances`, `./config:/app/config`, env_file `.env`)
- [x] Create `.dockerignore`, `.gitignore` (ignore `instances/temp/*`, `.env`, `__pycache__`)
- [x] Create skeleton dirs: `src/detector/`, `src/prompt/`, `src/cli/`, `src/action/`, `tasks/`, `instances/temp/`, `instances/permanent/`, `config/` (no `src/llm/` — opencode via `src/cli/` is the adapter)
- [x] Create placeholder `config/SOUL.md`, `config/AGENT.md`, `config/USER.md`, `config/ENTRY.md`, `config/SKILL.md`
- [x] Verify: `docker compose build && docker compose run --rm banana echo "ok"` — built 150.1s, `ok` 2026-09-17

**Exit criteria:** Container builds and runs. `AGENTS.md:5` respected. ✅

---

## Phase 1 — Detector (Triggers)
**Goal:** `plan.md:54-63` — accept Message + CRON and emit normalized `Given`.

- [x] Define `Given` schema: `src/detector/schema.json` -> `{id, source: "gui|telegram|cron", timestamp, text, meta}`
- [x] Implement `src/detector/detector.py`:
  - `from_message(text, source)` -> Given
  - `from_cron(cron_expr, task_ref)` -> Given (use `croniter` or node-cron, minimal)
- [x] Add simple CLI entry: `python -m src.detector --message "do X"` and `--cron "*/5 * * * *"`
- [x] Test in Docker: `docker compose run --rm banana python -m src.detector --message "test job"` — gui ✅, cron ✅, invalid cron ✅ 2026-09-17

**Exit criteria:** Both triggers produce valid Given JSON to stdout/file. ✅

---

## Phase 2 — Prompt Builder
**Goal:** `plan.md:67-96` — Given + Context + System -> single prompt string.

- [x] Implement `src/prompt/builder.py`:
  - `load_system()` reads `config/SOUL.md`, `AGENT.md`, `USER.md`, `ENTRY.md` (dedupe SKILL.md — pick one canonical location, log warning if both exist)
  - `load_context(given)` pulls relevant files/commands/instances (start simple: include `instances/permanent/*` + referenced task README)
  - `build(given)` -> `prompt.md` string: `System\n---\nContext\n---\nGiven`
- [x] Keep prompt small — truncate context to 4k tokens max, log token estimate
- [x] Test in Docker: feed Phase 1 Given -> inspect built prompt output — `System+Context+Given` verified 2026-09-17

**Exit criteria:** Deterministic prompt file generated from any Given. ✅

---

## Phase 3 — CLI Code (opencode) — LLM Adapter
**Goal:** `plan.md:100-113` — opencode IS the LLM. No separate provider. Prompt -> opencode -> ACTION.

- [x] Install opencode in `Dockerfile` (e.g., `npm i -g opencode-ai` or official install script, verify `opencode --version` inside container) — 1.18.31 ✅
- [x] Implement `src/cli/opencode.py` (or `wrapper.py`):
  - Function `run(prompt: str) -> {raw_text, exit_code}` — writes prompt to temp file, invokes `opencode run --prompt-file <file>` (or `opencode exec`) inside container — adapted to `opencode run --format json <prompt>` (verified CLI)
  - Config: opencode reads auth/model from `opencode.json` / env mounted via `.env` + `config/` — no direct `LLM_API_KEY` handling in code
  - Parse opencode output for action block (e.g., ```bash fences or JSON `{"action": "run_task", "task": "task-1", "args": {}}`)
  - MVP keeps it simple: opencode must return `TASK: <task-name>` + args, wrapper validates task exists in `/tasks`
- [x] Handle errors: timeout 120s, retry 1x, return error JSON (don't crash pipeline) — mock + timeout logic ✅
- [x] Test in Docker: `docker compose run --rm banana python -m src.cli --prompt "hello"` and `opencode --version` — `1.18.31`, mock `TASK: echo-demo` ✅ 2026-09-17

**Exit criteria:** Prompt in -> opencode text out -> validated task invocation, all inside container. ✅

---

## Phase 4 — ACTION + Tasks + Instances
**Goal:** `plan.md:117-200` — actually do work and persist state.

- [x] Implement `src/action/executor.py`:
  - `execute(task_name, args, instance_id)` -> runs `tasks/{name}/run.sh` or `run.py` inside container
  - Timeout 60s, capture stdout/stderr, return `{status, output, error}`
  - All writes confined to `/app/instances` and `/app/tasks`
- [x] Create example tasks:
  - `tasks/echo-demo/run.sh` (echo args)
  - `tasks/hello-py/run.py` (simple python job)
  - Each with `README.md` (inputs/outputs)
- [x] Implement instance handling `src/action/instances.py`:
  - `create_temp(given, result)` -> `instances/temp/{uuid}/context.json` with `created_at`
  - `create_permanent(...)` -> `instances/permanent/{id}/`
  - Reaper: `instances_reaper.py` deletes `instances/temp/*` older than 72h (`plan.md:143`), check `plan.md:152` — ask LLM or keep flag before delete (MVP: just log and keep if `keep: true`)
- [x] Test in Docker: end-to-end `Given -> prompt -> mock LLM -> execute echo-demo -> instance created` — echo-demo ✅, hello-py ✅, temp instance `/app/instances/temp/108d9fb2...` ✅, reaper dry-run 0 2026-09-17

**Exit criteria:** Task executes, output returned, instance file persists correctly. ✅

---

## Phase 5 — Glue & Return Path (MVP Close)
**Goal:** `plan.md:204-223` — wire full pipeline.

- [ ] Create main entry `src/main.py`: `detector -> prompt builder -> cli (opencode) -> action -> save instance -> print result`
- [ ] Support: `docker compose run --rm banana python -m src.main --message "run echo-demo hello"`
- [ ] Support CRON mode: `docker compose run --rm banana python -m src.main --cron-mode` (loops or single tick with croniter)
- [ ] Add `TASKS` reference from instance to task (`instances/{id}/TASKS` symlink or `context.json.tasks`)

**Exit criteria:** `plan.md:253-266` all MVP bullets demonstrable inside Docker (via opencode).

---

## Phase 6 — Polish (Post-MVP, only if needed)

- [ ] Telegram adapter `src/detector/telegram.py`
- [ ] GUI webhook stub
- [ ] Logging to `instances/logs/`
- [ ] Minimal tests `tests/test_e2e.py` run inside Docker

---

## Execution Rules for Agents

1. **Read before code:** `plan.md` + `AGENTS.md` + current phase in this file.
2. **Docker first:** Any manual test must be `docker compose run` — never `python` on host.
3. **One phase PR:** Don't start Phase N+1 until Phase N exit criteria pass in container.
4. **Mark progress:** Update checkboxes in this file after each phase.
5. **Keep state file-based:** No DB, no queue. See `AGENTS.md:6`.

## Current Status

- Phase: 4 - done (2026-09-17)
- Last run: sudo docker compose run --rm banana python -m src.action --task echo-demo -> ok, instance 108d9fb2 created
- Next action: Begin Phase 5 — Glue & Return Path (MVP Close)
