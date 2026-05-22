# garmin-sync

Downloads health and fitness data from Garmin Connect into a local DuckDB file for analysis and MCP tooling.

Part of the [Personalkin](../Personalkin) ecosystem — sits alongside SpendWisely (spending) and MyCalendar (events) as a data source that Personalkin's MCP server reads from.

---

## What it syncs

| Table | Granularity | Key fields |
|---|---|---|
| `health_days` | One row per date | Sleep stages, HRV, resting HR, stress, Body Battery, SpO2, steps, calories, training readiness, endurance score, fitness age |
| `health_activities` | One row per workout | Activity type, duration, HR zones, training load, aerobic/anaerobic effect |

Data is fetched via the unofficial Garmin Connect API (`garminconnect` library). No FIT file parsing — daily-granularity JSON endpoints only.

---

## Setup

```bash
# 1. Clone and create virtualenv
python3 -m venv .venv
pip install -r requirements.txt

# 2. Create .env with Garmin credentials
cp .env.example .env
# edit .env: GARMIN_EMAIL and GARMIN_PASSWORD

# 3. Authenticate (first time only)
.venv/bin/python auth.py
# Session saved to .garth/ — subsequent runs skip login entirely
```

**If auth hits rate limits (429):** Use a VPN (US server works), then retry. Garmin rate-limits login attempts per IP.

---

## Usage

```bash
# Sync yesterday + today (default — run daily)
.venv/bin/python sync.py

# Sync a specific date
.venv/bin/python sync.py --date 2026-05-15

# Backfill last N days (run once after setup)
.venv/bin/python sync.py --backfill 365

# Explore raw API responses for a date (dumps JSON to data/raw/)
.venv/bin/python explore.py --date 2026-05-21
```

Syncs are idempotent — re-running the same date overwrites existing rows.

---

## Automating with cron

```bash
# Add to crontab: sync daily at 8am
crontab -e

# Paste:
0 8 * * * cd /Users/yourname/Projects/garmin-sync && .venv/bin/python sync.py >> /tmp/garmin-sync.log 2>&1
```

---

## Output

The sync writes to `garmin.duckdb` in the project root (gitignored). Personalkin's MCP tools read from this file at `~/Projects/garmin-sync/garmin.duckdb`.

---

## Credentials

Set in `.env` (gitignored):

```
GARMIN_EMAIL=your@email.com
GARMIN_PASSWORD=yourpassword
```

Session tokens are saved in `.garth/` (gitignored) after first login. Never committed to source.
