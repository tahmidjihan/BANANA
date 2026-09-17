# AGENTS.md — Banana Bot

> Instructions for any AI agent (Claude Code, Codex, OpenCode, etc.) working in this repo.

## 1. What Banana Is

Minimal personal automation bot. Not OpenClaw. Not a general autonomous agent.

Core job: `Give Banana a job and let it get the job done.` See `plan.md:3-13`.

**Runtime constraint:** Whole thing will run INSIDE docker container. See `plan.md:247-249`. All code, deps, and actions must be container-compatible. Never assume host access.

## 2. Architecture to Respect

```
Message / CRON -> Detector -> Prompt (Given + Context + System) -> CLI Code (opencode) -> ACTION -> /TASKS <-> /INSTANCES
```
`opencode` IS the LLM adapter — no separate LLM provider. See `plan.md:204-223` and `plan.md:20-37`.

Do not change this pipeline without updating `plan.md`.

## 3. Project Structure (target)

```
/
├── plan.md
├── AGENTS.md        # this file
├── WORKFLOW.md      # execution plan for agents
├── Dockerfile
├── docker-compose.yml
├── src/
│   ├── detector/    # triggers: message, cron
│   ├── prompt/      # Given/Context/System builder
│   ├── llm/         # (deprecated - use cli/opencode, kept for legacy)
│   ├── cli/         # wrapper for opencode (LLM adapter)
│   └── action/      # task executor (python/node/bash)
├── tasks/           # executable jobs
├── instances/
│   ├── temp/        # auto-expire after 72h
│   └── permanent/   # persist until deleted
└── config/
    ├── SOUL.md
    ├── AGENT.md
    ├── USER.md
    ├── ENTRY.md
    └── SKILL.md
```

If a directory doesn't exist yet, create it as needed per `WORKFLOW.md` phase.

## 4. Principles (from plan.md:228-243)

1. Minimalism — build only what is needed
2. Job first — get work done
3. Use existing tools — wrap, don't reimplement CLI agents
4. Keep state simple — file-based instances
5. Keep tasks executable — python/node/bash
6. Don't build OpenClaw
7. Containerized — everything runs in Docker

## 5. How Agents Must Work

### Before coding
- Read `plan.md`, `AGENTS.md`, `WORKFLOW.md` fully.
- Check `WORKFLOW.md` for current phase. Do not skip phases.
- Verify Docker context: `docker --version` and that changes work inside container.

### While coding
- One phase at a time. Mark phase checklist in `WORKFLOW.md` when done.
- Prefer editing existing files over creating new ones.
- Keep prompts small: System (SOUL/AGENT/USER) + Context (relevant files) + Given (trigger). Don't dump whole repo into context.
- All ACTION execution must be via `src/action/` and assume container filesystem.
- Use file-based state for instances. Temp instances: JSON/MD with `created_at`, expire after 72h via reaper. No DB.

### After coding
- Test inside Docker: `docker compose build && docker compose run --rm banana <test>`
- Update `WORKFLOW.md` status.
- Do not commit secrets. Opencode auth via `.env` / opencode config mounted as env vars (no direct LLM API keys).

## 6. File Contracts

- `config/*.md`: System prompts. Agents read but don't overwrite without approval.
- `tasks/{name}/`: Must contain `run.sh` or `run.py` + `README.md` describing inputs/outputs.
- `instances/temp/{id}/`: Contains `context.json` + `TASKS` reference. TTL 72h.
- `instances/permanent/{id}/`: Same, no TTL.

## 7. Don't

- Don't add frameworks, queues, or DBs unless MVP `plan.md:253-267` proves need.
- Don't run host-level commands outside Docker.
- Don't expand MVP scope.

## 8. Current Status

- Phase 0 not started. See `WORKFLOW.md` for execution order.
