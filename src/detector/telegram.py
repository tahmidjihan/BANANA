"""Telegram adapter — WORKFLOW.md:108 (Phase 6)
Place your BotFather token in .env as TELEGRAM_BOT_TOKEN

Polling MVP: python -m src.detector.telegram --poll
Webhook stub: telegram.py also exports from_update() -> Given
"""
import os
import json
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import requests  # if not present, polling falls back to stdlib http
except ImportError:
    requests = None


def token_from_env() -> str | None:
    try:
        from src.creds import load_creds
        c=load_creds()
        if c.get("TELEGRAM_BOT_TOKEN"):
            return c["TELEGRAM_BOT_TOKEN"]
    except Exception:
        pass
    return os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")


def from_update(update: dict) -> dict:
    """Convert Telegram update JSON -> Given (via detector)"""
    from .detector import from_message
    # update can be message or edited_message
    msg = update.get("message") or update.get("edited_message") or update.get("channel_post") or {}
    text = msg.get("text") or msg.get("caption") or ""
    # if no text, try update itself
    if not text and "text" in update:
        text = update["text"]
    chat = msg.get("chat", {})
    user = msg.get("from", {})
    meta = {
        "telegram_update_id": update.get("update_id"),
        "chat_id": chat.get("id"),
        "user_id": user.get("id"),
        "username": user.get("username"),
    }
    # clean None
    meta = {k: v for k, v in meta.items() if v is not None}
    if not text:
        text = json.dumps(update, ensure_ascii=False)[:500]
    return from_message(text, source="telegram", meta_extra=meta)


def get_updates(token: str, offset: int = 0, timeout: int = 30) -> list:
    if requests is None:
        import urllib.request, urllib.parse
        url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout={timeout}"
        with urllib.request.urlopen(url, timeout=timeout+5) as r:
            data = json.loads(r.read().decode())
            return data.get("result", [])
    else:
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"offset": offset, "timeout": timeout}, timeout=timeout+10)
        r.raise_for_status()
        return r.json().get("result", [])


def send_message(token: str, chat_id: int | str, text: str):
    if requests is None:
        import urllib.request, urllib.parse
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        with urllib.request.urlopen(url, data=data, timeout=10) as r:
            return json.loads(r.read().decode())
    else:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": text}, timeout=10)
        r.raise_for_status()
        return r.json()


def poll_loop(token: str | None = None, mock: bool = False):
    """Poll Telegram and run pipeline for each message (MVP)."""
    if mock:
        # mock mode: simulate one update without needing token
        fake = {"update_id": 1, "message": {"text": "run echo-demo hello via telegram", "chat": {"id": 123}, "from": {"id": 1, "username": "test"}}}
        from src.prompt.builder import build
        from src.cli.opencode import run as cli_run
        from src.action.executor import execute
        from src.action.instances import create_temp
        given = from_update(fake)
        print(f"[MOCK] Given: {json.dumps(given, indent=2)}")
        prompt = build(given)
        cli_res = cli_run(prompt, mock=True)
        task = cli_res.get("task") or "echo-demo"
        result = execute(task, cli_res.get("args") or {"msg": "telegram mock"})
        inst = create_temp(given, result)
        print(f"[MOCK] Result: {result['output']} instance={inst}")
        return

    token = token or token_from_env()
    if not token:
        print("TELEGRAM_BOT_TOKEN not set in .env — see .env.example", flush=True)
        print("Get token from @BotFather on Telegram: /newbot -> copy token -> put in .env", flush=True)
        return

    allowed = os.getenv("TELEGRAM_ALLOWED_CHAT_ID") or os.getenv("TELEGRAM_ALLOWED_USER_ID")
    if allowed:
        print(f"Allow-list: only chat_id={allowed} will be processed", flush=True)
    else:
        print("No TELEGRAM_ALLOWED_CHAT_ID set — bot will reply to ANYONE who knows its username (set it in .env to restrict to you)", flush=True)

    print(f"Polling Telegram as bot {token[:6]}... (Ctrl+C to stop)", flush=True)
    offset = 0
    while True:
        try:
            updates = get_updates(token, offset=offset, timeout=30)
            for upd in updates:
                offset = upd["update_id"] + 1
                given = from_update(upd)
                chat_id = str(given["meta"].get("chat_id") or "")
                user_id = str(given["meta"].get("user_id") or "")
                if allowed and chat_id != str(allowed) and user_id != str(allowed):
                    print(f"[TG] ignored chat={chat_id} user={user_id} (not allowed)", flush=True)
                    continue
                print(f"[TG] {given['id']} text={given['text'][:80]} chat={given['meta'].get('chat_id')}", flush=True)
                # run full pipeline via src.main
                from src.main import _run_once
                out = _run_once(given, mock=False)
                # reply
                chat_id = given["meta"].get("chat_id")
                if chat_id:
                    reply = out["result"].get("output") or out["result"].get("error") or "done"
                    try:
                        send_message(token, chat_id, reply[:4000])
                    except Exception as e:
                        logger.warning("send failed: %s", e)
            if not updates:
                time.sleep(1)
        except KeyboardInterrupt:
            print("stopped")
            break
        except Exception as e:
            logger.error("poll error: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Telegram poll")
    p.add_argument("--poll", action="store_true", help="start polling")
    p.add_argument("--mock", action="store_true", help="mock one update without token")
    p.add_argument("--token", type=str, default="", help="override token")
    args = p.parse_args()
    if args.mock:
        poll_loop(token=args.token or "mock", mock=True)
    elif args.poll or True:
        poll_loop(token=args.token or None)
