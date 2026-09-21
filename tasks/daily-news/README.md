# daily-news

Fetches top headlines for **technology, science, and politics** and sends them to
your Telegram chat. Built for the daily run at **05:00 Asia/Dhaka (UTC+6)**.

## Inputs (optional JSON via `$1` / stdin)

- `topics` (list[string], default `["technology","science","politics"]`) — Google News RSS search terms
- `per_topic` (int, default `5`, max `8`) — headlines per topic
- `chat_id` (string) — Telegram chat id to send to (default: `TELEGRAM_ALLOWED_CHAT_ID` from `.env` / `config/creds.json`)
- `dry` (bool, default `false`) — print the digest to stdout instead of sending

## Outputs

- `stdout`: JSON `{task, topics, headlines, dry_run, chat_id, message_ids, errors}`
- When `dry: true`: the digest text + JSON summary
- Telegram: one message with 🌅 header + top headlines per topic (title + link,
  split across messages if over Telegram's 4096-char limit)

## Run

```bash
python tasks/daily-news/run.py '{}'                # send to TELEGRAM_ALLOWED_CHAT_ID
python tasks/daily-news/run.py '{"dry":true}'     # preview digest, don't send
python tasks/daily-news/run.py '{"topics":["tech","science"]}'
python -m src.action --task daily-news --args '{"dry":true}'
```

News source: Google News RSS (`news.google.com/rss/search`) — free, no API key.
Creds: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALLOWED_CHAT_ID` (see `.env.example`).

## Scheduling — every 5 AM Dhaka (GMT+6)

Host crontab with `CRON_TZ=Asia/Dhaka`:

```cron
CRON_TZ=Asia/Dhaka
0 5 * * * cd /home/tahmidjihan/Documents/Folders/BANANA && docker compose run --rm banana python tasks/daily-news/run.py '{}' >> /tmp/banana-daily-news.log 2>&1
```

Or as UTC time (23:00 UTC = 05:00 Dhaka next day):

```cron
0 23 * * * cd /home/tahmidjihan/Documents/Folders/BANANA && docker compose run --rm banana python tasks/daily-news/run.py '{}' >> /tmp/banana-daily-news.log 2>&1
```

Or via the Banana pipeline (cron mode):

```bash
docker compose run --rm banana python -m src.main --cron '0 5 * * *' --task daily-news
```