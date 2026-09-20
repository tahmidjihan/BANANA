"""Creds loader — JSON file editable via UI, fallback to .env/env vars
Priority: env var > config/creds.json > .env file
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CREDS_JSON = ROOT / "config" / "creds.json"
ENV_FILE = ROOT / ".env"

_DEFAULTS = {
    "OPENCODE_MODEL": "opencode/big-pickle",
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_ALLOWED_CHAT_ID": "",
    "TELEGRAM_ALLOWED_USER_ID": "",
    "OLLAMA_HOST": "http://host.docker.internal:11434",
}

def _load_dotenv():
    d = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k,v=line.split("=",1)
            d[k.strip()] = v.strip()
    return d

def load_creds() -> dict:
    data = dict(_DEFAULTS)
    # json file first (editable)
    if CREDS_JSON.exists():
        try:
            j=json.loads(CREDS_JSON.read_text())
            for k,v in j.items():
                if k in _DEFAULTS or k in ("OPENCODE_MODEL","TELEGRAM_BOT_TOKEN","TELEGRAM_ALLOWED_CHAT_ID","TELEGRAM_ALLOWED_USER_ID","OLLAMA_HOST"):
                    data[k]=str(v) if v is not None else ""
            # also allow any extra keys
            for k,v in j.items():
                if k not in data:
                    data[k]=str(v)
        except Exception as e:
            print(f"warn: failed to load {CREDS_JSON}: {e}")
    # .env fallback for missing
    dotenv=_load_dotenv()
    for k in list(data.keys()):
        if not data[k] and dotenv.get(k):
            data[k]=dotenv[k]
    # env vars override (process env always wins)
    for k in list(data.keys()):
        if os.getenv(k):
            data[k]=os.getenv(k)
    # also include any env that looks like creds
    for k in ("OPENCODE_MODEL","TELEGRAM_BOT_TOKEN","TELEGRAM_ALLOWED_CHAT_ID","TELEGRAM_ALLOWED_USER_ID","OLLAMA_HOST","OPENCODE_API_KEY","ANTHROPIC_API_KEY"):
        if os.getenv(k) and k not in data:
            data[k]=os.getenv(k)
    return data

def get_cred(key: str, default=""):
    return load_creds().get(key, default)

def save_creds(updates: dict) -> dict:
    """Merge updates into creds.json, return new data"""
    data={}
    if CREDS_JSON.exists():
        try: data=json.loads(CREDS_JSON.read_text())
        except: data={}
    for k,v in updates.items():
        # sanitize key
        k=k.strip()
        if not k or ".." in k or "/" in k:
            continue
        data[k]=str(v) if v is not None else ""
    CREDS_JSON.parent.mkdir(parents=True, exist_ok=True)
    CREDS_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    # also sync to env for current process
    for k,v in data.items():
        os.environ[k]=str(v)
    return load_creds()

# auto-sync to env on import
try:
    _c=load_creds()
    for k,v in _c.items():
        if v and not os.getenv(k):
            os.environ[k]=v
except Exception:
    pass
