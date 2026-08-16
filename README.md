# garmin-sync

Your Garmin data, in plain SQL.

Pulls sleep, HRV, training load, Body Battery, and workout history from Garmin Connect into a local DuckDB file — queryable with any SQL tool, notebook, or AI assistant.

```sql
-- How does training load affect recovery?
SELECT date, sleep_score, training_readiness_score, hrv_last_night
FROM   health_days
ORDER BY date DESC LIMIT 30;

-- Which activity type leaves you most recovered the next day?
SELECT   a.activity_type,
         ROUND(AVG(d.hrv_last_night), 1) AS next_day_hrv
FROM     health_activities a
JOIN     health_days d ON d.date = a.date + INTERVAL 1 DAY
GROUP BY a.activity_type
ORDER BY next_day_hrv DESC;
```

> **Unofficial API** — uses [`garminconnect`](https://github.com/cyberjunky/python-garminconnect), which wraps Garmin Connect's undocumented internal API. Personal use only.

---

## How it works

```
Garmin Connect  ──[ garminconnect ]──▶  sync.py  ──▶  garmin.duckdb
```

`sync.py` calls each endpoint, extracts fields, and upserts into DuckDB. Re-running the same date is safe — all syncs are idempotent.

---

## Data model

### `health_days` — one row per calendar date

| Category | Fields |
|---|---|
| Sleep | `sleep_score`, `sleep_total_min`, `sleep_deep_min`, `sleep_rem_min`, `sleep_spo2_avg`, `sleep_rr_avg` |
| HRV | `hrv_last_night`, `hrv_weekly_avg`, `hrv_baseline_low/high`, `hrv_status` |
| Heart rate | `rhr`, `hr_min`, `hr_max`, `stress_avg` |
| Body Battery | `bb_max`, `bb_min`, `bb_end` |
| Movement | `steps`, `distance_km`, `floors_up`, `calories_total` |
| Respiration | `spo2_avg`, `spo2_min`, `rr_waking_avg` |
| Training | `training_readiness_score`, `training_status_phrase`, `acwr_status`, `recovery_time_hours`, `endurance_score`, `fitness_age` |

### `health_activities` — one row per workout

| Field | Notes |
|---|---|
| `activity_type` | `running`, `strength_training`, `cycling`, `boxing`, … |
| `duration_min`, `distance_km`, `avg_pace_min_km` | pace is null for non-GPS activities |
| `avg_hr`, `max_hr` | |
| `hr_zone1_min` … `hr_zone5_min` | minutes in each HR zone |
| `training_load`, `training_effect_aerobic`, `training_effect_anaerobic` | 0–5 scale for effects |

---

## Setup

```bash
git clone https://github.com/Yegor-M/garmin-sync.git
cd garmin-sync
cp .env.example .env        # add GARMIN_EMAIL and GARMIN_PASSWORD
python3 setup.py            # deps → auth → backfill → physiology
```

`setup.py` is idempotent — safe to re-run if any step fails.

> **Rate limits:** Garmin returns 429 on too many login attempts from one IP. Wait 30–60 min or use a US VPN, then retry.

<details>
<summary>Manual steps</summary>

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python auth.py
.venv/bin/python sync.py --backfill 30
.venv/bin/python fetch_physiology.py   # optional: age, weight, race preds, PRs
```

</details>

---

## Usage

```bash
.venv/bin/python sync.py                      # yesterday + today
.venv/bin/python sync.py --date 2026-05-15    # specific date
.venv/bin/python sync.py --backfill 365       # last N days
.venv/bin/python explore.py --date 2026-05-21 # dump raw JSON to data/raw/
.venv/bin/python fetch_physiology.py          # refresh profile + race predictions
```

---

## Automation

**macOS — launchd** (fires on wake, unlike cron):

```xml
<!-- ~/Library/LaunchAgents/com.garmin-sync.daily.plist -->
<key>ProgramArguments</key><array>
    <string>/path/to/garmin-sync/.venv/bin/python</string>
    <string>/path/to/garmin-sync/sync.py</string>
</array>
<key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>8</integer>
    <key>Minute</key><integer>0</integer>
</dict>
```

```bash
launchctl load ~/Library/LaunchAgents/com.garmin-sync.daily.plist
```

**Linux — cron:**

```bash
0 8 * * * cd /path/to/garmin-sync && .venv/bin/python sync.py >> /tmp/garmin-sync.log 2>&1
```

---

## Use with Personalkin

[Personalkin](https://github.com/Yegor-M/Personalkin) is an MCP server that connects AI assistants directly to your Garmin data. Point its `GARMIN_DB` env var at `garmin.duckdb` and ask questions in plain language — "How did I sleep this week?", "Show last week's training load" — from Claude, Cursor, or any MCP-compatible client.
