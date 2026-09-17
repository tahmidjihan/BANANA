"""Prompt Builder — plan.md:67-96, WORKFLOW.md:43-53
Given + Context + System -> single prompt string
Keep small: truncate context to 4k tokens (~16k chars), log estimate
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Paths assume container /app but work on host too (BANANA root)
ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
TASKS_DIR = ROOT / "tasks"
INSTANCES_PERM = ROOT / "instances" / "permanent"

SYSTEM_FILES = ["SOUL.md", "AGENT.md", "USER.md", "ENTRY.md", "SKILL.md"]
MAX_TOKENS = 4000
CHARS_PER_TOKEN = 4
MAX_CHARS = MAX_TOKENS * CHARS_PER_TOKEN  # ~16k


def _read_md(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.warning("missing %s", path)
        return ""


def load_system(config_dir: Path | None = None) -> str:
    """Load System prompt — WORKFLOW.md:47
    Reads config/SOUL.md etc. Dedupe SKILL.md: if both config/SKILL.md and ROOT/SKILL.md exist, prefer config and warn.
    """
    cfg = Path(config_dir) if config_dir else CONFIG_DIR
    # dedupe SKILL.md
    root_skill = ROOT / "SKILL.md"
    cfg_skill = cfg / "SKILL.md"
    if root_skill.exists() and cfg_skill.exists():
        logger.warning("SKILL.md exists in both %s and %s — using %s", root_skill, cfg_skill, cfg_skill)

    parts = []
    for name in SYSTEM_FILES:
        p = cfg / name
        # skip root SKILL if cfg one exists (dedupe)
        if name == "SKILL.md" and cfg_skill.exists() and p != cfg_skill:
            continue
        txt = _read_md(p)
        if txt:
            parts.append(f"## {name}\n{txt}")
    if not parts:
        logger.warning("no system files found in %s", cfg)
    return "\n\n".join(parts)


def load_context(given: dict, max_chars: int = MAX_CHARS) -> str:
    """Load Context — WORKFLOW.md:48
    Simple MVP: instances/permanent/* + referenced task README if text hints task name.
    """
    pieces = []

    # 1) permanent instances
    if INSTANCES_PERM.exists():
        for child in sorted(INSTANCES_PERM.iterdir()):
            if child.name.startswith("."):
                continue
            ctx = child / "context.json"
            if ctx.exists():
                try:
                    data = json.loads(ctx.read_text(encoding="utf-8"))
                    pieces.append(f"### Instance {child.name}\n```json\n{json.dumps(data, indent=2)[:2000]}\n```")
                except Exception as e:
                    logger.warning("bad instance %s: %s", ctx, e)
            # also show TASKS ref if exists
            tasks_ref = child / "TASKS"
            if tasks_ref.exists():
                try:
                    pieces.append(f"### Instance {child.name} TASKS\n{tasks_ref.read_text()[:1000]}")
                except Exception:
                    pass

    # 2) task README hint — if given text contains a task name, include its README
    text = (given.get("text") or "") + " " + json.dumps(given.get("meta") or {})
    if TASKS_DIR.exists():
        for task_dir in sorted(TASKS_DIR.iterdir()):
            if task_dir.is_dir() and not task_dir.name.startswith("."):
                # hint: task name appears in text
                if task_dir.name in text:
                    readme = task_dir / "README.md"
                    if readme.exists():
                        pieces.append(f"### Task {task_dir.name}\n{readme.read_text(encoding='utf-8')[:2000]}")
        # if no hint match, still list available tasks (small)
        if not any("### Task" in p for p in pieces):
            available = [d.name for d in TASKS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")]
            if available:
                pieces.append(f"### Available tasks\n{', '.join(sorted(available))}")

    ctx = "\n\n".join(pieces) if pieces else "No additional context."
    # token estimate + truncate
    est_tokens = len(ctx) // CHARS_PER_TOKEN
    logger.info("context ~%d tokens (%d chars)", est_tokens, len(ctx))
    if len(ctx) > max_chars:
        logger.warning("truncating context %d -> %d chars (4k tokens)", len(ctx), max_chars)
        ctx = ctx[:max_chars] + "\n\n[truncated to 4k tokens]"
    return ctx


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def build(given: dict, config_dir: Path | None = None, max_chars: int = MAX_CHARS) -> str:
    """Build full prompt — WORKFLOW.md:49"""
    from src.detector.detector import validate

    validate(given)
    system = load_system(config_dir)
    context = load_context(given, max_chars=max_chars)
    given_str = json.dumps(given, indent=2, ensure_ascii=False)

    prompt = f"""# SYSTEM
{system}

---
# CONTEXT
{context}

---
# GIVEN
```json
{given_str}
```

Instructions: Use SYSTEM + CONTEXT + GIVEN to decide next ACTION. Follow ENTRY.md output contract (TASK: <name> + ARGS).
"""
    logger.info("prompt built ~%d tokens", estimate_tokens(prompt))
    return prompt
