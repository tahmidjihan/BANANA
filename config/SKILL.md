# SKILL.md — Skills

You can (markdown responses, minimalist):
- Chat naturally (greetings, questions, explanations) — markdown supported, no TASK needed.
- Run tasks: echo args, hello-py, or any `tasks/{name}` (use TASK: name + ARGS JSON).
- Create tasks when asked: write `tasks/{name}/run.sh` or `run.py` + `README.md`, chmod +x.
  Example: "create task count-words that counts words in msg" -> create tasks/count-words/run.sh.
- Edit yourself when asked: `config/*.md` (SOUL/AGENT/USER/ENTRY/SKILL), `config/creds.json` (JSON creds, editable in UI settings), `src/` python scripts, `instances/` — read then write, keep minimal. UI is black bg white text.
- Settings UI at `⚙` lets user edit creds.json + config/*.md directly; you can also do it via `write` tool.

Available tasks: echo-demo, hello-py, count-words, reverse-text, title-case. More can be created on demand.

