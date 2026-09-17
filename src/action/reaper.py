"""Reaper entry — WORKFLOW.md:87
python -m src.action.reaper [--dry-run]
"""
from .instances import reap_temp

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    removed = reap_temp(dry_run=args.dry_run)
    print(f"reaped {len(removed)}: {removed}")
