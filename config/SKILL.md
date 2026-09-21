# SKILL.md — Skills

You can (markdown responses, minimalist):
- Chat naturally (greetings, questions, explanations) — markdown supported, no TASK needed.
- Run tasks: echo args, hello-py, or any `tasks/{name}` (use TASK: name + ARGS JSON).
- Create tasks when asked: write `tasks/{name}/run.sh` or `run.py` + `README.md`, chmod +x.
  Example: "create task count-words that counts words in msg" -> create tasks/count-words/run.sh.
- Edit yourself when asked: `config/*.md` (SOUL/AGENT/USER/ENTRY/SKILL), `config/creds.json` (JSON creds), `instances/chats/{id}/chat.json` (chats — you are aware of current chat, can create/delete), `src/` python scripts — read then write, keep minimal. UI is black bg white text.
- Settings UI at `⚙` lets user edit creds.json + config/*.md; Chats sidebar lets you create/delete chats, agent does same via `instances/chats/`.

Available tasks: echo-demo, hello-py, count-words, reverse-text, title-case, daily-news (5 AM Dhaka telegram news digest). More can be created on demand.

