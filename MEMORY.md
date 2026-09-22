# MEMORY.md — Banana's Recent Memories

> Auto-updated after each turn. Agent reads this every prompt. Keep minimal — file-based, 4k max.

## User
- Owner: Personal user. Minimal output, no fluff.
- What Banana knows: (add as you learn) — e.g., name, preferences, timezone Asia/Dhaka

## How to Run Tasks
- `echo-demo`: `bash tasks/echo-demo/run.sh '{"msg":"hello"}'` or `run echo-demo hello`
- `hello-py`: `python tasks/hello-py/run.py '{"msg":"hello"}'`
- `count-words`: `bash tasks/count-words/run.sh '{"msg":"hello world"}'` → `2`
- `reverse-text`: `bash tasks/reverse-text/run.sh '{"msg":"hello"}'` → `olleh`
- `title-case`: `bash tasks/title-case/run.sh '{"msg":"hello world"}'` → `Hello World`
- `daily-news`: `python tasks/daily-news/run.py '{"dry_run":true}'` → digest without Telegram

## Recent Topics
- (auto) No topics yet — will store last 10 discussions

## Recent Task Runs
- (auto) No runs yet

## Preferences
- Language: English (concise)
- Style: Brutal minimalist, black/white, borders
- Port: 4242 (42×101 double Answer)

## Notes
- Chats: `instances/chats/{id}/chat.json` — current chat history also in CONTEXT
- Creds: `config/creds.json` — editable via UI ⚙
- Self-edit: `config/*.md`, `tasks/*`, `src/*`, `instances/*` via `write` + `--auto`
