# garmin-sync

Sync your Garmin Connect health and fitness data to a local [DuckDB](https://duckdb.org) file you can query with plain SQL.

> **Unofficial API:** This project uses [`garminconnect`](https://github.com/cyberjunky/python-garminconnect), which wraps Garmin Connect's undocumented internal web API. Endpoints may change without notice. Intended for personal use only — your own data, not others'.

---

Garmin Connect holds years of your health data — sleep stages, HRV, training load, Body Battery, heart rate — but gives you no good way to query it. garmin-sync pulls it into a local DuckDB file on a daily schedule so you can ask real questions:

```sql
-- Sleep quality vs training load
SELECT date, sleep_score, training_readiness_score, hrv_last_night
FROM health_days ORDER BY date DESC LIMIT 30;

-- Which activity types leave you most recovered the next day?
SELECT a.activity_type, ROUND(AVG(d.hrv_last_night), 1) AS next_day_hrv
FROM health_activities a
JOIN health_days d ON d.date = a.date + INTERVAL 1 DAY
GROUP BY a.activity_type ORDER BY next_day_hrv DESC;
```

Works standalone as a SQL data source for notebooks, dashboards, or custom scripts. Also the health data backend for [Personalkin](https://github.com/Yegor-M/personalkin), an MCP server for AI assistants.

---

## How it works

```
Garmin Connect (cloud)
        │
        │  garminconnect  ·  unofficial REST API
        ▼
    sync.py
        │
        ├── health_days          one row per calendar date
        │   sleep · HRV · RHR   steps · stress · Body Battery
        │   SpO2 · training readiness · training status
        │
        └── health_activities    one row per workout
            type · duration · HR zones · pace · training load
        │
        ▼
   garmin.duckdb  ──►  SQL queries · notebooks · MCP tools
```

Each sync is idempotent — re-running a date safely overwrites existing rows.

---

## Data model

### `health_days` — one row per calendar date

| Category | Fields |
|---|---|
| Sleep | `sleep_score`, `sleep_qualifier`, `sleep_total_min`, `sleep_deep_min`, `sleep_rem_min`, `sleep_light_min`, `sleep_awake_min`, `sleep_spo2_avg`, `sleep_rr_avg` |
| HRV | `hrv_last_night`, `hrv_weekly_avg`, `hrv_baseline_low/high`, `hrv_status` |
| Heart rate | `rhr`, `hr_min`, `hr_max` |
| Body Battery | `bb_max`, `bb_min`, `bb_end` |
| Movement | `steps`, `step_goal`, `distance_km`, `floors_up`, `calories_total/active/bmr` |
| Intensity | `moderate_activity_min`, `vigorous_activity_min` |
| Respiration | `spo2_avg`, `spo2_min`, `rr_waking_avg` |
| Training | `training_readiness_score/level`, `recovery_time_hours`, `endurance_score`, `fitness_age` |
| Training status | `training_status_phrase`, `training_load_balance`, `acwr_status` |

### `health_activities` — one row per workout

| Field | Notes |
|---|---|
| `activity_type` | `running`, `strength_training`, `cycling`, `boxing`, etc. |
| `duration_min`, `distance_km` | |
| `avg_hr`, `max_hr` | |
| `hr_zone1_min` … `hr_zone5_min` | Minutes spent in each HR zone |
| `avg_pace_min_km` | Null for non-GPS activities (strength, MMA, etc.) |
| `training_load` | Garmin's composite training stress score |
| `training_effect_aerobic`, `training_effect_anaerobic` | 0–5 scale |

---

## Setup

```bash
# 1. Clone and install
git clone https://github.com/Yegor-M/garmin-sync.git
cd garmin-sync
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Add credentials
cp .env.example .env
# Edit .env — fill in GARMIN_EMAIL and GARMIN_PASSWORD

# 3. Authenticate (first time only)
.venv/bin/python auth.py
# Session saved to .garth/ — subsequent runs reuse it without re-authenticating
```

> **Rate limits:** Garmin returns 429 if login is attempted too frequently from one IP. If this happens, wait 30–60 minutes or use a VPN (US server), then retry.

---

## Usage

```bash
# Sync yesterday + today (default — catches late-arriving data)
.venv/bin/python sync.py

# Sync a specific date
.venv/bin/python sync.py --date 2026-05-15

# Backfill last N days (run once after setup)
.venv/bin/python sync.py --backfill 365

# Inspect raw API responses for a date (writes JSON to data/raw/)
.venv/bin/python explore.py --date 2026-05-21
```

---

## Automation

### macOS — launchd (recommended)

Unlike cron, launchd fires on wake if the Mac was asleep at the scheduled time.

Create `~/Library/LaunchAgents/com.garmin-sync.daily.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.garmin-sync.daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>/absolute/path/to/garmin-sync/.venv/bin/python</string>
        <string>/absolute/path/to/garmin-sync/sync.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>8</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key><string>/tmp/garmin-sync.log</string>
    <key>StandardErrorPath</key><string>/tmp/garmin-sync.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>GARMIN_EMAIL</key><string>your@email.com</string>
        <key>GARMIN_PASSWORD</key><string>yourpassword</string>
    </dict>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.garmin-sync.daily.plist
launchctl list | grep garmin-sync   # verify it's registered
```

### Linux — cron

```bash
0 8 * * * cd /path/to/garmin-sync && .venv/bin/python sync.py >> /tmp/garmin-sync.log 2>&1
```

---

## Use with Personalkin

[Personalkin](https://github.com/Yegor-M/personalkin) is an MCP server that connects AI assistants to your personal data. Point its `GARMIN_DB` env var at `garmin.duckdb` and it can answer questions about your sleep, training, and recovery directly in Claude, Cursor, or any MCP-compatible client.
