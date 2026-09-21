# daily-news

Fetch top headlines about **tech, science, and politics** and send them to your Telegram every day at **05:00 Asia/Dhaka (UTC+6)**.

Fully free, no API keys. Primary source: **Google News RSS topic search** (`news.google.com/rss/search`). Fallback if Google News is unreachable: curated RSS feeds — Hacker News, TechCrunch (tech); ScienceDaily, NASA (science); BBC World + Politics.

## Inputs (`ARGS` JSON in `$1` or stdin)

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `dry_run` / `dry` | bool | `false` | print digest instead of sending to Telegram |
| `chat_id` | int/str | creds | override Telegram chat id (default: `TELEGRAM_ALLOWED_CHAT_ID` from `config/creds.json`/`.env`; if empty, auto-detects the most recent chat that messaged the bot) |
| `categories` / `topics` | list or `"tech,science"` | all | subset of `tech`, `science`, `politics` |
| `limit` / `per_topic` | int (1–5) | `3` | headlines per category |

## Outputs

- `stdout`: JSON `{status, chat_id, categories, headlines, preview}` — `status` is `sent` or `dry_run`
- `stderr`: the full digest text (so the pipeline captures the message)
- Telegram: one digest message via the Bot API

## Run

```bash
# dry run (prints digest, no Telegram send)
python tasks/daily-news/run.py '{"dry_run": true}'
python -m src.action --task daily-news --args '{"dry_run": true}'

# real send — to chat from creds (TELEGRAM_ALLOWED_CHAT_ID) or auto-detected
python -m src.action --task daily-news --args '{}'
```

## Schedule — 05:00 Dhaka daily

Registered in `config/schedule.json`. 05:00 Dhaka (UTC+6) = **23:00 UTC previous day**.

Host crontab with `CRON_TZ=Asia/Dhaka`:

```cron
CRON_TZ=Asia/Dhaka
0 5 * * * cd /home/tahmidjihan/Documents/Folders/BANANA && docker compose run --rm banana python -m src.main --cron '0 5 * * *' --task daily-news --source cron >> /tmp/banana-daily-news.log 2>&1
```

Or in UTC terms (23:00 UTC = 05:00 Dhaka next day):

```cron
0 23 * * * cd /home/tahmidjihan/Documents/Folders/BANANA && docker compose run --rm banana python -m src.main --cron '0 5 * * *' --task daily-news --source cron >> /tmp/banana-daily-news.log 2>&1
```

Or run the task directly:

```bash
docker compose run --rm banana python tasks/daily-news/run.py '{}'
```

## Requirements

- `TELEGRAM_BOT_TOKEN` in `config/creds.json` (or `.env`)
- `TELEGRAM_ALLOWED_CHAT_ID` — recommended; if empty, the task auto-picks the most recent chat that messaged the bot