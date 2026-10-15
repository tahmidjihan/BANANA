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

## Phase 8 — Multi-Step Jobs — DONE 2026-10-11
**Goal:** one Given can produce several tasks, chained, without changing the pipeline shape.

- [x] `src/action/plan.py` — parse `PLAN:` block and JSON `{"plan":[...]}` / `{"steps":[...]}`; line form `- step N: task {args} uses: $prev`
- [x] Validate whole plan **before** step 1: unknown task -> `not_found`, >10 steps -> `too_many_steps`, unresolvable `uses` -> `parse_error`
- [x] Step chaining: `uses: $prev` / `stepN` resolves to that step's stdout, capped at 2000 chars, bound as `_prev_output` (and `msg` when the step declares no args)
- [x] `src/cli/opencode.py` — `parse_output` returns `steps`; PLAN takes precedence over a bare TASK line
- [x] `run_job()` in `src/action/runner.py`; `run_steps()` resolves `uses` at execution time
- [x] Per-step traces: `instances/temp/{id}/steps/{n}.json` via `write_job_trace()`
- [x] `job_id` (the Given id) tags every step in `runs.jsonl`
- [x] Guardrails: max 10 steps, 300s job budget (`budget_exceeded`), `fail_fast` default
- [x] GUI: `steps` + `job` in `/api/chat`, collapsible JOB panel in the dashboard
- [x] Prompt side: `config/ENTRY.md` contract 3 + `config/AGENT.md` document the format so the agent emits it
- [x] Tests: `tests/test_plan.py` — 26 tests; full suite 46 passing in Docker

**Exit criteria:** met. Verified a 3-step chain (`echo-demo -> count-words -> reverse-text`) runs end-to-end with output chained and traces persisted, and a plan with a bad task in step 2 runs nothing.

**Deferred:** a step declaring `instance_id` to read/write a permanent instance. The `PLAN:` format has no such field yet; add it when a real job needs it rather than speculating.

**Note:** `Dockerfile` opencode install was made non-fatal after `opencode.ai` became unreachable from this network (2026-10-11). The image builds and all tests pass without it; real LLM runs will error until opencode is installed.

---

## Phase 9 — Boot Jobs + Persisted Scheduler — DONE 2026-10-14
**Goal:** deploy Banana once; it starts doing work on its own. No manual CLI invocations.

### 9a — Job registry
- [x] `config/jobs.json` (file-based, no DB — `AGENTS.md:5`): `{id, kind, schedule, task, args, enabled, timeout, retries, created_at, last_run_at, boot_completed_at}`
- [x] `src/scheduler/registry.py` — load/validate/save, cron validation via `croniter`, atomic write with a direct-write fallback (bind-mounted file cannot be renamed onto)
- [x] CRUD used by CLI + GUI, same file

### 9b — Boot jobs
- [x] `src/scheduler/boot.py` — runs enabled `kind=boot` jobs on start, sequentially, `delay_seconds` stagger, non-fatal per job
- [x] Wired into `docker-entrypoint.sh` before the GUI, logging to `instances/logs/boot.log`
- [x] `boot_completed_at` recorded; `SKIP_BOOT_JOBS=1` escape hatch

### 9c — Cron loop
- [x] `src/scheduler/daemon.py` — real `croniter` due-detection replacing the fixed 60s tick at `src/main.py:192-198`; tick 30s
- [x] `last_run_at` persisted so restarts inside the window don't double-fire; `DUE_WINDOW_SECONDS=90` stops stale jobs replaying on every start
- [x] Daily reaper tick
- [x] Started from entrypoint as a background process; log at `instances/logs/scheduler.log`; `--once` / `--status` for manual use
- [x] Entry point only fires for gui/telegram/all modes, so one-shot commands don't spawn a scheduler

**Exit criteria:** met. `docker compose up` runs the boot job and starts the daemon with no manual `python -m src.main`; logs land in `instances/logs/{boot,scheduler}.log` and `runs.jsonl`.

**Verified:** boot-echo ran on start with `boot_completed_at` set; `* * * * *` job fired exactly once per minute across two ticks.

**Config:** `SKIP_BOOT_JOBS=1` skips boot jobs, `NO_SCHEDULER=1` disables the daemon, `scheduler` mode runs the daemon in the foreground.

---

## Phase 10 — Jobs UI — DONE 2026-10-15
**Goal:** one place in the dashboard to see and control every kind of job.

- [x] `GET /api/jobs` -> jobs grouped `{cron, boot, webhook}` + `next_run` per job + scheduler health
- [x] `POST /api/jobs` (400 on invalid cron), `PUT /api/jobs/{id}`, `DELETE /api/jobs/{id}` (404 if missing)
- [x] `POST /api/jobs/{id}/run` run-now, `POST /api/jobs/{id}/toggle` enable/disable
- [x] `GET /api/jobs/{id}/runs` -> run history for that job, matched by `job_run_id` prefix
- [x] JOBS overlay (sidebar link + header button), one table per kind: id / schedule / task / last run / toggle / RUN·HIST·DEL, inline create form with task dropdown + args JSON
- [x] Per-job history rows expand under the job with OK/ERR tag, retry count, duration, output tail
- [x] Scheduler health line: running, tick, ticks, fired, last tick, stall reason
- [x] Empty state per kind + cron syntax hint

**Exit criteria:** met. Verified over HTTP against the running container: create (201), invalid cron (400), toggle, update, run-now, run history, delete (200/404), and `/api/jobs` returning live scheduler state.

**Verification gap (honest):** the JSX compiles under Babel and the panel markup is served, and every endpoint was exercised over HTTP — but the dashboard was **not** driven in a real browser (none available here; React/Babel load from CDN). Interactive behaviour is unverified by machine.

**Bug fixed here:** `daemon.status()` reflects only the current process, so the GUI always showed the scheduler as stopped. Added an `instances/logs/scheduler.json` heartbeat written each tick and read by the GUI (stalled after 180s).

---

## All phases complete

Phase 0–10 done. Suite: **91 tests passing** inside Docker (`docker compose run --rm banana python -m pytest tests/ -q`).

Outstanding, not blocking:
- No real (non-`--mock`) opencode run verified — `opencode.ai` has been intermittently unreachable.
- No browser-level UI test.
- `tests/test_e2e.py` (full pipeline through the GUI) still open.
- Phase 8 deferred: a step declaring `instance_id` to target a permanent instance.

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

- Phase: **all 0–10 done** (2026-10-15) — suite is 91 passing
- Last run: `docker compose up` -> boot job ran, daemon fired 2 jobs, GUI reports `running: true` via heartbeat
- Next action: none required — see "Outstanding" above
- Blockers: `opencode.ai` flaky — **no real (non-`--mock`) opencode run verified yet**
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
| Multi-step plans | `src/action/plan.py` |
| Jobs / scheduler | `config/jobs.json`, `src/scheduler/{registry,jobs,boot,daemon}.py` |
| Tests | `tests/` (`python -m pytest tests/ -q`) |
| Instance state | `src/action/instances.py`, `src/action/reaper.py` |
| Jobs (new, Phase 9) | `config/jobs.json`, `src/scheduler/*` |
| Dashboard | `src/gui/server.py`, `src/gui/static/index.html` |
| Container start | `docker-entrypoint.sh` |
