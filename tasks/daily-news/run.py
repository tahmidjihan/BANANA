#!/usr/bin/env python3
"""daily-news — top headlines (tech / science / politics) delivered to Telegram.

Scheduled: every day 05:00 Asia/Dhaka (UTC+6) via cron -> this task (see README.md).
Stdlib only (urllib + xml.etree) so it runs in the minimal container.
Inputs:  $1 JSON {"topics":[...], "per_topic":N, "chat_id":"...", "dry":bool}
Outputs: stdout JSON summary (+ digest when dry:true), Telegram message on send.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_TOPICS = ["technology", "science", "politics"]
TOPIC_LABELS = {
    "technology": "TECHNOLOGY",
    "tech": "TECHNOLOGY",
    "techworld": "TECHNOLOGY",
    "science": "SCIENCE",
    "politics": "POLITICS",
    "world": "WORLD",
    "global": "WORLD",
}
MAX_MESSAGE = 3900  # telegram limit is 4096; keep headroom


def _topic_label(topic: str) -> str:
    return TOPIC_LABELS.get(topic.lower(), topic.upper())


def _env(key: str) -> str:
    """Creds lookup: env var -> config/creds.json -> .env file (same order as src/creds.py)."""
    v = os.getenv(key)
    if v:
        return v.strip()
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from src.creds import get_cred
        v = get_cred(key, "")
        if v:
            return str(v).strip()
    except Exception:
        pass
    for root in (REPO_ROOT, Path.cwd()):
        f = root / ".env"
        if not f.exists():
            continue
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, val = line.partition("=")
                if k.strip() == key:
                    return val.strip()
        except OSError:
            continue
    return ""


def fetch_google_news(topic: str, limit: int = 5) -> list:
    """Top headlines for a topic via Google News RSS (free, no API key)."""
    url = (
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode({"q": topic, "hl": "en", "gl": "US", "ceid": "US:en"})
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (BananaBot/1.0)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    root = ET.fromstring(raw)
    items = []
    for el in root.iter():
        if not el.tag.endswith("item"):
            continue
        fields = {}
        for child in el:
            tag = child.tag.rsplit("}", 1)[-1]
            fields.setdefault(tag, child.text or "")
        title = fields.get("title", "").strip()
        link = fields.get("link", "").strip()
        source = fields.get("source", "").strip()
        # Google News appends " - SourceName" to titles; strip it when known
        if source and title.lower().endswith((" - " + source).lower()):
            title = title[: -len(" - " + source)].strip()
        if not title or not link:
            continue
        items.append({"title": title, "link": link, "source": source})
        if len(items) >= limit:
            break
    return items


def build_digest(topics: list, sections: dict) -> str:
    lines = ["🌅 *Daily News Brief* — 5 AM Dhaka (UTC+6)", ""]
    for topic in topics:
        items = sections.get(topic, [])
        lines.append(f"*{_topic_label(topic)}*")
        if not items:
            lines.append("(no headlines found)")
        for i, it in enumerate(items, 1):
            src = f" — {it['source']}" if it.get("source") else ""
            lines.append(f"{i}. {it['title']}{src}")
            lines.append(f"   {it['link']}")
        lines.append("")
    return "\n".join(lines).strip()


def send_telegram(token: str, chat_id: str, text: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def main():
    raw = sys.argv[1] if len(sys.argv) > 1 else ""
    if not raw and not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
    args = {}
    if raw.strip().startswith("{"):
        try:
            args = json.loads(raw)
        except json.JSONDecodeError:
            pass

    topics = [str(t).strip().lower() for t in (args.get("topics") or DEFAULT_TOPICS) if str(t).strip()]
    if not topics:
        topics = DEFAULT_TOPICS
    per_topic = max(1, min(int(args.get("per_topic") or 5), 8))
    dry = bool(args.get("dry"))
    chat_id = str(args.get("chat_id") or _env("TELEGRAM_ALLOWED_CHAT_ID") or "").strip()

    # fetch headlines
    sections = {}
    fetched = 0
    errors = []
    for topic in topics:
        try:
            sections[topic] = fetch_google_news(topic, per_topic)
            fetched += len(sections[topic])
        except Exception as e:  # noqa: BLE001 — one topic failing shouldn't kill the digest
            errors.append(f"{topic}: {e}")
            sections[topic] = []

    digest = build_digest(topics, sections)
    if len(digest) > MAX_MESSAGE:
        digest = digest[:MAX_MESSAGE].rsplit("\n", 1)[0] + "\n(…truncated)"

    summary = {
        "task": "daily-news",
        "topics": topics,
        "headlines": fetched,
        "dry_run": dry,
        "chat_id": chat_id or "(unset)",
        "errors": errors,
    }

    if dry or not chat_id:
        if not chat_id and not dry:
            print("error: no chat_id — set TELEGRAM_ALLOWED_CHAT_ID in .env/creds.json or pass chat_id arg", file=sys.stderr)
            sys.exit(1)
        print(digest)
        print()
        print(json.dumps(summary, ensure_ascii=False))
        return

    token = _env("TELEGRAM_BOT_TOKEN")
    if not token:
        print("error: TELEGRAM_BOT_TOKEN not found (env / config/creds.json / .env)", file=sys.stderr)
        sys.exit(1)

    # telegram 4096-char limit — split if needed
    sent = []
    body = digest
    while body:
        chunk = body[:MAX_MESSAGE]
        body = body[MAX_MESSAGE:]
        resp = send_telegram(token, chat_id, chunk)
        msg = resp.get("result") or resp
        sent.append(msg.get("message_id"))
    summary["message_ids"] = sent
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()