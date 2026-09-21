#!/usr/bin/env python3
"""daily-news — fetch top tech / science / politics headlines and send to Telegram.

Scheduled: every day 05:00 Asia/Dhaka (UTC+6) — see config/schedule.json.
Free RSS sources only (no API keys): Hacker News, TechCrunch, ScienceDaily,
NASA, BBC World + BBC Politics.

Run:
    python tasks/daily-news/run.py '{"dry_run": true}'
    python -m src.action --task daily-news --args '{"dry_run": true}'

Args (JSON in $1):
    dry_run    bool   print digest instead of sending (default false)
    chat_id    int|str  override Telegram chat (default: creds TELEGRAM_ALLOWED_CHAT_ID,
                        else auto-resolve to the most recent chat that messaged the bot)
    categories list   subset of tech/science/politics (default all)
    limit      int    headlines per category (default 3)

Output (stdout): JSON {status, chat_id?, dry_run, categories, headlines, preview}
"""
import json
import sys
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

# allow running standalone (host or container): repo root on sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import requests as _requests
except Exception:  # pragma: no cover
    _requests = None

# Dhaka is UTC+6, no DST — fixed offset is safe and avoids tzdata dependency
DHAKA = timezone(timedelta(hours=6))

# Google News RSS topic searches (free, no API key) — best match for the user's
# "top news about tech / science / politics" ask. Curated FEEDS below are fallback.
GOOGLE_TOPICS = {
    "tech": "technology",
    "science": "science",
    "politics": "politics",
}

FEEDS = {
    "tech": [
        "https://hnrss.org/frontpage",
        "https://techcrunch.com/feed/",
    ],
    "science": [
        "https://www.sciencedaily.com/rss/top/science.xml",
        "https://www.nasa.gov/rss/dyn/breaking_news.rss",
    ],
    "politics": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.bbci.co.uk/news/politics/rss.xml",
    ],
}

ICONS = {"tech": "💻", "science": "🔬", "politics": "🌍"}


def _get(url: str, timeout: int = 8) -> str:
    if _requests is not None:
        r = _requests.get(url, timeout=timeout, headers={"User-Agent": "BananaBot/1.0"})
        r.raise_for_status()
        return r.text
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "BananaBot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _clean(text: str) -> str:
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", "", text)          # strip tags
    t = re.sub(r"\s+", " ", t).strip()        # collapse whitespace
    return t[:140]


def _parse_feed(xml_text: str) -> list[tuple[str, str]]:
    """Parse RSS2.0 or Atom -> list of (title, url)."""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    # RSS 2.0
    for item in root.iter("item"):
        title = _clean(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        if title and link:
            items.append((title, link))
    if items:
        return items
    # Atom
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        title = _clean(entry.findtext("{http://www.w3.org/2005/Atom}title") or "")
        link_el = entry.find("{http://www.w3.org/2005/Atom}link")
        link = (link_el.get("href") if link_el is not None else "") or ""
        if title and link:
            items.append((title, link))
    return items


def _fetch_google_news(query: str, limit: int) -> list[tuple[str, str]]:
    """Top headlines via Google News RSS search — free, no API key."""
    import urllib.parse
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "en", "gl": "US", "ceid": "US:en"}
    )
    root = ET.fromstring(_get(url))
    items = []
    for item in root.iter("item"):
        title = _clean(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        source = (item.findtext("source") or "").strip() or \
            (item.findtext("{http://www.w3.org/2005/Atom}source/{http://www.w3.org/2005/Atom}name") or "").strip()
        if not title or not link:
            continue
        # Google News appends " - SourceName" to titles; strip it when known
        if source and title.lower().endswith((" - " + source).lower()):
            title = title[: -len(" - " + source)].rstrip()
        items.append((title, link))
        if len(items) >= limit:
            break
    return items


def fetch_news(categories: list[str], limit: int) -> dict[str, list[tuple[str, str]]]:
    """Fetch headlines per category: Google News topic search first, curated RSS fallback."""
    out = {}
    for cat in categories:
        seen, got = set(), []

        def _add(iterable):
            for title, link in iterable:
                key = title.lower()
                if key in seen:
                    continue
                seen.add(key)
                got.append((title, link))

        try:
            _add(_fetch_google_news(GOOGLE_TOPICS.get(cat, cat), limit))
        except Exception:
            pass
        if not got:  # fallback: curated feeds if Google News failed
            for url in FEEDS.get(cat, []):
                try:
                    _add(_parse_feed(_get(url)))
                except Exception:
                    continue  # one bad feed shouldn't kill the digest
        out[cat] = (got or [])[:limit]
    return out


def build_digest(news: dict[str, list[tuple[str, str]]], limit: int) -> str:
    now = datetime.now(DHAKA)
    date_fmt = now.strftime("%A, %d %b %Y — %I:%M %p")
    lines = [f"🌅 Good morning! Daily digest — {date_fmt} (Dhaka UTC+6)", ""]
    for cat in ("tech", "science", "politics"):
        items = news.get(cat) or []
        if not items:
            continue
        lines.append(f"{ICONS.get(cat, '📰')} {cat.upper()}")
        for i, (title, link) in enumerate(items[:limit], 1):
            lines.append(f"{i}. {title}")
            lines.append(f"   🔗 {link}")
        lines.append("")
    if len(lines) <= 3:
        raise RuntimeError("no headlines fetched from any feed — check network/feeds")
    lines.append("— Banana Bot 🍌")
    return "\n".join(lines)


def _resolve_chat_id(token: str, chat_id) -> str:
    """chat_id arg > creds TELEGRAM_ALLOWED_CHAT_ID > most recent bot chat."""
    if chat_id not in (None, ""):
        return str(chat_id)
    from src.creds import get_cred
    cred = get_cred("TELEGRAM_ALLOWED_CHAT_ID", "")
    if cred:
        return str(cred)
    # auto: latest chat that messaged the bot
    try:
        if _requests is not None:
            r = _requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"timeout": 2}, timeout=10)
            data = r.json().get("result", [])
        else:
            import urllib.request, urllib.parse
            url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=2"
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read().decode()).get("result", [])
        for upd in reversed(data):
            msg = upd.get("message") or upd.get("channel_post") or {}
            cid = msg.get("chat", {}).get("id")
            if cid is not None:
                return str(cid)
    except Exception:
        pass
    raise RuntimeError(
        "no Telegram chat_id configured. Set TELEGRAM_ALLOWED_CHAT_ID in config/creds.json "
        "(or message the bot once so the chat can be auto-detected)."
    )


def send_digest(text: str, chat_id: str, dry_run: bool) -> dict:
    if dry_run:
        return {"status": "dry_run", "chat_id": chat_id}
    from src.creds import get_cred
    token = get_cred("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set in config/creds.json")
    try:
        from src.detector.telegram import send_message
        send_message(token, int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id, text)
    except Exception:
        # direct fallback (avoid circular import issues in odd setups)
        if _requests is not None:
            r = _requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": text}, timeout=10)
            r.raise_for_status()
    return {"status": "sent", "chat_id": chat_id}


def main():
    raw = sys.argv[1] if len(sys.argv) > 1 else ""
    if not raw and not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
    args = {}
    if raw.strip().startswith("{"):
        try:
            args = json.loads(raw)
        except Exception:
            args = {"msg": raw}
    # aliases keep compat with the earlier interface: dry ~ dry_run,
    # per_topic ~ limit, topics ~ categories
    dry_run = bool(args.get("dry_run", args.get("dry", False)))
    chat_id = args.get("chat_id")
    try:
        limit = max(1, min(int(args.get("limit", args.get("per_topic", 3))), 5))
    except Exception:
        limit = 3
    categories = args.get("categories") or args.get("topics") or ["tech", "science", "politics"]
    if isinstance(categories, str):
        categories = [c.strip() for c in categories.split(",") if c.strip()]
    categories = [c for c in categories if c in FEEDS] or ["tech", "science", "politics"]

    news = fetch_news(categories, limit)
    digest = build_digest(news, limit)

    from src.creds import get_cred
    token = get_cred("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set in config/creds.json")
    cid = _resolve_chat_id(token, chat_id)
    result = send_digest(digest, cid, dry_run)
    result.update({
        "categories": categories,
        "headlines": sum(len(v) for v in news.values()),
        "preview": digest[:200] + ("…" if len(digest) > 200 else ""),
    })
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if dry_run:
        print("\n--- DIGEST PREVIEW (dry run) ---\n", file=sys.stderr)
    else:
        print(f"\n[daily-news] sent to chat {cid}", file=sys.stderr)
    print(digest, file=sys.stderr)


if __name__ == "__main__":
    main()