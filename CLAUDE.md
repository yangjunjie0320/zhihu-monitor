# Zhihu Monitor

Async Python service monitoring multiple Zhihu users (answers, pins, and
articles) via Zhihu API v4, pushing Feishu notifications to per-user webhooks.
Single Docker container, supercronic, every 11 minutes. NEVER use any emoji.

## Commands

```bash
docker compose up --build -d                      # Start
docker compose run --rm monitor python main.py    # Manual trigger
```

## Tech Stack

Python 3.12-slim, httpx (async), playwright (async Chromium), diskcache,
python-dotenv, supercronic. Frozen `dataclasses` (no Pydantic). Code in English.

## Architecture

```
zhihu_monitor/
├── main.py              # Entrypoint, loops targets, asyncio.run()
├── config.py            # Frozen dataclass from env; sole os.environ reader
├── models.py            # MonitorTarget, Item
├── constants.py         # ContentType/NotificationType enums
├── services/
│   ├── zhihu.py         # API v4 client, field mapping
│   ├── webhook.py       # Feishu card builder + POST
│   ├── history.py       # Persistent content version history (JSON)
│   ├── screenshot.py    # Playwright full-page capture
│   └── archive.py       # Article JSON save, age-based cleanup
├── utils/
│   ├── cache.py         # diskcache.Cache factory (/app/data/cache)
│   ├── state.py         # Per-user seen_ids + timestamps
│   ├── cookies.py       # Netscape cookie parser, expiry check
│   ├── text.py          # Strip HTML, extract summary
│   ├── time.py          # UTC/Beijing conversion
│   └── logging.py       # TimedRotatingFileHandler, 7-day retention
├── crontab
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

`services/` = external integrations. `utils/` = shared infra, no API calls.
`main.py` = only file importing across boundaries.

## Multi-User Config

`MONITOR_TARGETS` env var: JSON array mapping users to webhooks.
Parsed into `list[MonitorTarget]`. `main.py` loops independently; one
target failing does not block others.

```json
[
  {"user_id": "shui-qian-xiao-xi", "user_name": "马前卒", "webhook_url": "https://...hook/aaa"},
  {"user_id": "another-user",      "user_name": "用户名", "webhook_url": "https://...hook/bbb"}
]
```

## Data Models (`models.py`)

```python
@dataclass(frozen=True)
class MonitorTarget:
    user_id: str
    webhook_url: str
    user_name: str = ""              # Display name for notifications

    @property
    def display_name(self) -> str:
        return self.user_name or self.user_id

@dataclass(frozen=True)
class Item:
    id: str
    content_type: ContentType
    title: str
    url: str
    summary: str                     # Plain text, max 200 chars
    created_time: datetime           # Beijing timezone
    has_images: bool = False
    content_hash: str = ""           # MD5 of content for diff detection
```

## Zhihu API v4 (`services/zhihu.py`)

Three endpoints per user, cookies required:

```
GET /api/v4/members/{uid}/answers
  ?include=data[*].content,excerpt,created_time,updated_time,
   voteup_count,comment_count,question.title
  &limit=5&offset=0&sort_by=created

GET /api/v4/members/{uid}/pins
  ?include=data[*].content,created,updated,comment_count,reaction_count
  &limit=5&offset=0

GET /api/v4/members/{uid}/articles
  ?include=data[*].content,excerpt,created,updated,voteup_count,
   comment_count,image_url,title
  &limit=5&offset=0&sort_by=created
```

Headers: desktop UA, `Referer: https://www.zhihu.com/people/{uid}`,
`x-requested-with: fetch`. Cookies as header string `k1=v1; k2=v2`.

**Field mapping** (inside `zhihu.py` only, never expose raw dicts):

Answers: `id`=str(raw["id"]), `title`=raw["question"]["title"],
`url`=question.id+answer.id, `summary`=strip_html(raw["excerpt"]),
`created_time`=raw["created_time"] (Beijing tz),
`has_images`="<img" in raw["content"].

Pins: content is JSON array of blocks (`text`, `image`, `link`, `video`).
First text block for title/summary. Unknown block types: skip, not crash.

Articles: `id`=str(raw["id"]), `title`=raw["title"],
`url`=zhuanlan.zhihu.com/p/{id}, `summary`=strip_html(raw["excerpt"]),
`created_time`=raw["created"] (Beijing tz).

## Content History (`services/history.py`)

Persistent JSON-based version history per item:
`{data_dir}/history/{user_id}/{item_id}.json`

Each file stores: item_id, content_type, url, first_seen, and a list of
versions (timestamp, content_hash, title, summary). Never deleted.

`record_batch()` returns (new_items, updated_items) by comparing
content_hash against the latest recorded version.

## Cookies (`utils/cookies.py`)

Netscape format. Crash if missing at startup. Two output formats: header
string (httpx) and list-of-dicts with `domain: ".zhihu.com"` (Playwright).
Expiry reminder via first target's webhook (1x per 5 days, 7-day threshold).

## Per-User State (`utils/state.py`)

All state in diskcache, namespaced by user_id:

| Key | TTL |
|---|---|
| `state:{uid}:seen_ids` | None, `set[str]`, cap 1000, trim oldest |
| `state:{uid}:last_check` | None |
| `state:{uid}:last_new_content` | None |
| `state:{uid}:last_error_report` | None |
| `state:{uid}:errors` | 24h |
| `state:last_cookie_reminder` | None, global |

API responses NOT cached (need fresh data every run).

## Pipeline (`main.py`)

```
load_settings() -> list[MonitorTarget]
CookieManager.load() -> check expiry, remind if needed
for each target:
    ZhihuClient.fetch_all(target.user_id)
    compare against content history -> new/updated items
    for each new: archive + screenshot
    webhook.send(target.webhook_url, new_items)
    update seen_ids, trim to 1000
    if silent for SILENCE_HOURS -> silence reminder
    if errors -> error report (rate limited per user)
archive.cleanup(max_age_days)
```

## Notifications

| Type | Trigger | Rate limit |
|---|---|---|
| New content | New answer/pin/article | Every time |
| Updated content | Content hash changed | Archived only (no webhook) |
| Silence | No content for `SILENCE_HOURS` | Once per trigger |
| Error | Fetch failure | 1x per 24h per user |
| Cookie expiry | Expires within 7 days | 1x per 5 days |
| Debug | `DEBUG_MODE=true` | Every run |

## Error Handling

| Scenario | Action |
|---|---|
| Cookie file missing/unparseable | exit 1 |
| API non-2xx (partial) | WARN, collect, continue to next type/user |
| API response shape changed | ERROR with raw snippet, collect |
| Screenshot fails | WARN, skip, notify without image |
| Webhook fails | ERROR with body, raise |

No broad `try/except` around the pipeline.

## Environment Variables

| Variable | Default |
|---|---|
| `MONITOR_TARGETS` | required |
| `COOKIE_FILE` | `/app/cookies/zhihu.com_cookies.txt` |
| `DATA_DIR` | `/app/data` |
| `LOG_DIR` | `/app/data/logs` |
| `DEBUG_MODE` | `false` |
| `ARCHIVE_MAX_DAYS` | `30` |
| `SILENCE_HOURS` | `72` |
| `ERROR_REPORT_INTERVAL_HOURS` | `24` |
| `COOKIE_REMINDER_INTERVAL_DAYS` | `5` |

## Git

Remote: `git@github.com:yangjunjie0320/zhihu-monitor.git`, branch `main`.
`.gitignore`: `.env`, `.cache/`, `data/`, `logs/`, `cookies/`.
Track `.env.example`. All AI changes: commit and push to `origin/main`.

## Docker

Single container, supercronic as PID 1. Two-stage Dockerfile: fetch supercronic
(sha1 verify) then python:3.12-slim + deps + playwright chromium. Mount `./data`
+ `./cookies` (read-only).

## Fragile Points

1. **Zhihu API v4** undocumented, may change silently.
2. **Cookies** ~30 day lifespan, 401 or silent empty data when expired.
3. **Pin block types** may expand; unknown types skip, not crash.
4. **Playwright** needs 512MB+ memory in Docker.
5. **seen_ids cap** 1000: long gaps may miss content. By design.