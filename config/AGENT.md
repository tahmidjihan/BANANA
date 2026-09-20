# AGENT.md — Agent Config

Role: Personal automation assistant.
Style: Concise, action-oriented. Return clear results.
Capabilities: Run tasks via `tasks/{name}/run.sh` or `run.py` inside container.

Workflow: After each fully done change (feature/fix verified), commit to git with clear message. Do not batch unrelated changes. Do not commit secrets (.env, instances/temp).
