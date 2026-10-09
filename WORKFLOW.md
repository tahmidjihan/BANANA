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

- [x] Create main entry `src/main.py`: `detector -> prompt builder -> cli (opencode) -> action -> save instance -> print result`
- [x] Support: `docker compose run --rm banana python -m src.main --message "run echo-demo hello"` — mock ✅ `TASK echo-demo` 2026-09-18
- [x] Support CRON mode: `docker compose run --rm banana python -m src.main --cron-mode` (loops or single tick with croniter) — `*/5 * * * *` single tick ✅
- [x] Add `TASKS` reference from instance to task (`instances/{id}/TASKS` symlink or `context.json.tasks`) — `instances/temp/{id}/TASKS` + `context.json.tasks` ✅

**Exit criteria:** `plan.md:253-266` all MVP bullets demonstrable inside Docker (via opencode). ✅ MVP closed with --mock, real opencode requires auth.

---

## Phase 6 — Polish (Post-MVP) — MOSTLY DONE, re-audited 2026-10-09

- [x] Telegram adapter `src/detector/telegram.py` (built out of order, unverified in WORKFLOW)
- [x] GUI + TUI (`src/gui/server.py`, `src/tui/app.py`) — replaces the "webhook stub" idea
- [~] Logging to `instances/logs/` — dir exists, only telegram.log written. **Superseded by Phase 7 run log.**
- [x] Minimal tests — `tests/test_failures.py` (20 passing). Broader `tests/test_e2e.py` still open
- [ ] First real (non-`--mock`) opencode run end-to-end — everything so far verified with `--mock`

---

## Phase 7 — Failure Handling — DONE 2026-10-09
**Goal:** a failed step never kills the run silently, and every run leaves a trail.

- [x] `src/action/executor.py` — `retries` (default 1, backoff 2s) and per-task `timeout`/`retries` via `tasks/{name}/meta.json`
- [x] Classify failures: `timeout` | `nonzero_exit` | `not_found` | `invalid_args` | `spawn_error` via `classify_error()`
- [x] `src/action/runner.py` — `run_task()` absorbs every failure, `run_steps()` with `fail_fast` | `continue` policy (scaffolding for Phase 8)
- [x] Run log: every attempt appended to `instances/logs/runs.jsonl` with `job_id`, `attempt`, `error_kind`, `exit_code`, `duration_ms`, `output_tail`
- [x] Rotate at 5MB x 3 generations — rotates *before* append so the live file always survives
- [x] GUI: `GET /api/logs?limit&task&job_id&summary`, RUNS sidebar panel, `error_kind` badge on instance rows, `RETRIED ×N` + collapsible ERROR on messages
- [x] Fixtures: `tasks/fail-demo` (retries=2, exits non-zero), `tasks/slow-demo` (timeout=3s, sleeps 30)
- [x] Tests: `tests/test_failures.py` — 20 tests, all passing in Docker

**Exit criteria:** met. Every failure lands in `runs.jsonl` with an `error_kind`, retried per `meta.json`, visible in the GUI, and `python -m src.main` completes without raising when a task fails. Verified: fail-demo -> 3 attempts / `nonzero_exit`, slow-demo -> `timeout` / exit 124, missing task -> `not_found`.

---

## Phase 8 — Multi-Step Jobs
**Goal:** one Given can produce several tasks, chained, without changing the pipeline shape.

- [ ] Extend `src/cli/opencode.py` output contract: keep `TASK:` for single step, add a `PLAN:` block —
  `PLAN:` / `- step 1: task-name {args}` / `- step 2: task-name {args, uses: "<output of step 1>"}`
- [ ] `src/action/plan.py` — parse `PLAN:` into ordered steps; validate every `task_name` exists in `tasks/` **before** running step 1 (fail fast, `error_kind=parse_error`)
- [ ] Step chaining: `uses` resolves to previous step's stdout; cap output passed forward (e.g. 2k chars) to keep prompts small
- [ ] Per-step instances: write `instances/temp/{job_id}/steps/{n}.json`; final instance `context.json` holds the whole trace
- [ ] Job id: one id per Given (already in `schema.json`) reused across all steps; `job_id` added to every log line in Phase 7
- [ ] Reuse the instance: a step may declare `instance_id` to read/write a permanent instance instead of temp
- [ ] Guardrails: max 10 steps, max 300s total per job (constants, not config sprawl)
- [ ] Test in Docker: mock opencode returns 2-step PLAN -> both run, step 2 receives step 1 output, trace persisted

**Exit criteria:** A single message can run a 2+ step job with chained output, full trace in one instance, and a hard cap on steps/time.

---

## Phase 9 — Boot Jobs + Persisted Scheduler
**Goal:** deploy Banana once; it starts doing work on its own. No manual CLI invocations.

### 9a — Job registry
- [ ] New `config/jobs.json` (file-based, no DB — `AGENTS.md:5`): list of job objects
  `{id, kind: "cron"|"boot"|"webhook", schedule, task, args, enabled, timeout, retries, created_at}`
- [ ] `src/scheduler/registry.py` — load/validate/save `jobs.json`, atomic write (tmp + rename), reject bad cron via `croniter`
- [ ] CRUD helpers used by CLI + GUI so both edit the same file

### 9b — Boot jobs
- [ ] `src/scheduler/boot.py` — after container start, run every `enabled` job with `kind=boot`, sequentially, with `delay_seconds` stagger support
- [ ] Wire into `docker-entrypoint.sh` right before GUI `exec`, non-blocking-safe (log to `instances/logs/boot.log`)
- [ ] `boot_completed_at` recorded per job so restarts are visible; `--skip-boot-jobs` escape hatch for fast restarts and tests

### 9c — Cron loop
- [ ] `src/scheduler/daemon.py` — single long-running loop replacing the `--loop` 60s hack in `src/main.py:192-198`
- [ ] Uses `croniter` for real due-detection (persist `last_run_at` in `jobs.json` so restarts don't double-fire); tick 30s
- [ ] Also runs the reaper (`src/action/reaper.py`) on a daily tick
- [ ] Start from entrypoint as a background process alongside GUI/Telegram; PID + log file under `instances/logs/`

**Exit criteria:** `docker compose up` with one cron job + one boot job in `config/jobs.json` runs both without any manual `python -m src.main` call, survives restart without duplicate runs, and writes to the run log.

---

## Phase 10 — Jobs UI
**Goal:** one place in the dashboard to see and control every kind of job.

- [ ] `GET /api/jobs` -> all jobs grouped `{cron: [...], boot: [...], webhook: [...]}` + scheduler health (running?, last tick, jobs due)
- [ ] `POST /api/jobs` create, `PUT/DELETE /api/jobs/{id}`, `POST /api/jobs/{id}/run` run-now, `POST /api/jobs/{id}/toggle` enable/disable
- [ ] `GET /api/jobs/{id}/runs` -> last N runs from Phase 7 log for that job, with `error_kind` + retry count
- [ ] `src/gui/static/index.html` — add a **JOBS** panel (same black/white brutal style, no new deps):
  - one table for cron, one for boot, one for webhook
  - columns: id, schedule, task, enabled toggle, last run, status, actions (Run now / Edit / Delete)
  - inline create form: kind, cron expr or boot delay, task (dropdown from `/api/tasks`), args JSON
  - failed runs expandable -> stderr tail, attempts
- [ ] Polling: refresh jobs + run status every 10s (matches existing `loadMeta` pattern in `index.html:165`)
- [ ] Empty state: "NO JOBS — ADD ONE" with cron-syntax hint
- [ ] Test in Docker: create cron job in UI -> it appears in `/api/jobs` -> daemon fires it -> run shows in Jobs panel with status

**Exit criteria:** Cron, boot, and webhook jobs are all visible, creatable, toggleable, runnable, and show pass/fail history from the UI alone.

---

## Ordering

Phase 7 -> Phase 8 -> Phase 9 -> Phase 10. Hard rule: **do not start Phase 9 or 10 until Phase 7 exit criteria pass.** A scheduler that silently swallows failures is worse than no scheduler, and the Jobs UI is worthless if there is nothing reliable to display.

---

## Execution Rules for Agents

1. **Read before code:** `plan.md` + `AGENTS.md` + current phase in this file.
2. **Docker first:** Any manual test must be `docker compose run` — never `python` on host.
3. **One phase PR:** Don't start Phase N+1 until Phase N exit criteria pass in container.
4. **Mark progress:** Update checkboxes in this file after each phase.
5. **Keep state file-based:** No DB, no queue. See `AGENTS.md:6`.

## Current Status

- Phase: **7 done** (2026-10-09) — failure handling shipped with 20 passing tests
- Last run: `docker compose run --rm banana python -m pytest tests/ -q` -> 20 passed; fail-demo via `src.main` -> 3 attempts, `nonzero_exit`, no crash
- Next action: **Phase 8 — Multi-Step Jobs** (builds on `run_steps()` in `src/action/runner.py`)
- Blockers to keep in mind: everything verified so far used `--mock`; a real opencode run is still untested
- Note: Use `cd /home/tahmidjihan/Documents/Folders/BANANA` before docker compose (compose file not found from ~)

## Quick Reference — Where Things Live

| Concern | File |
|---|---|
| Pipeline glue | `src/main.py` |
| Triggers | `src/detector/detector.py`, `src/detector/telegram.py` |
| Prompt | `src/prompt/builder.py` |
| LLM adapter / output parsing | `src/cli/opencode.py` |
| Task execution | `src/action/executor.py` |
| Failure handling | `src/action/runner.py`, `src/action/logbook.py` |
| Tests | `tests/test_failures.py` (`python -m pytest tests/ -q`) |
| Instance state | `src/action/instances.py`, `src/action/reaper.py` |
| Jobs (new, Phase 9) | `config/jobs.json`, `src/scheduler/*` |
| Dashboard | `src/gui/server.py`, `src/gui/static/index.html` |
| Container start | `docker-entrypoint.sh` |
