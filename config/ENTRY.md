# ENTRY.md — Entry Instructions

Pipeline: Message/CRON -> Detector -> Prompt (Given+Context+System) -> CLI Code (opencode) -> ACTION

Output contract for opencode (Phase 3):
```
TASK: <task-name>
ARGS: { ...json... }
```
If no task matches, return explanation.
