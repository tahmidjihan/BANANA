"""Banana scheduler — WORKFLOW.md Phase 9

registry.py  config/jobs.json CRUD (single source of truth)
jobs.py      execute one job through the ACTION layer
boot.py      run kind=boot jobs on container start
daemon.py    long-running cron loop (croniter due-detection) + daily reaper
"""