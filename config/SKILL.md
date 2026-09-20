# SKILL.md — Skills

You can:
- Chat naturally (greetings, questions, explanations) — no TASK needed.
- Run tasks: echo args, hello-py, or any `tasks/{name}` (use TASK: name + ARGS JSON).
- Create tasks when asked: write `tasks/{name}/run.sh` or `run.py` + `README.md`, chmod +x.
Example ask: "create task count-words that counts words in msg" -> create tasks/count-words/run.sh that reads {"msg":"..."} and outputs word count.

Available tasks: echo-demo (bash echo), hello-py (python hello). More can be created on demand.

