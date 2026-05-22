# garmin-sync — Claude context

## Stack
Python 3.13, garminconnect 0.3.x (unofficial Garmin Connect API), DuckDB (read-write for sync, read-only for Personalkin MCP tools)
No FIT file parsing — daily-granularity JSON endpoints only.

## Key commands
```bash
# Authenticate (first time or if session expired)
.venv/bin/python auth.py

# Explore raw API responses for a date
.venv/bin/python explore.py --date 2026-05-21

# Sync a specific date
.venv/bin/python sync.py --date 2026-05-21

# Backfill last N days
.venv/bin/python sync.py --backfill 365

# Verify imports
.venv/bin/python -c "import sync; print('ok')"
```

## Project structure
```
auth.py              — get_client() → authenticated Garmin instance; session saved to .garth/
auth_interactive.py  — first-time auth fallback using garth.http.Client directly
explore.py           — calls all endpoints, dumps raw JSON to data/raw/ for inspection
sync.py              — fetches data for a date range and upserts into garmin.duckdb
schema.sql           — DuckDB table definitions; applied on every sync run (IF NOT EXISTS)
.env                 — gitignored; GARMIN_EMAIL and GARMIN_PASSWORD
.garth/              — gitignored; session tokens from garminconnect
data/raw/            — gitignored; JSON dumps from explore.py
garmin.duckdb        — gitignored; the output database read by Personalkin
```

## Key files
- `sync.py` — read before adding any endpoint; extraction pattern is `_extract_*(data) → dict`, called in `_fetch_day()`
- `schema.sql` — source of truth for column names; sync.py builds INSERT statements dynamically from dict keys, so column names must match exactly
- `explore.py` — run this on a new date after adding endpoints to verify responses before wiring into sync.py

## Adding a new endpoint
1. Add the call to `explore.py` endpoints list
2. Run `explore.py` to see the raw JSON
3. Write an `_extract_*()` helper in `sync.py` mapping raw keys → column names
4. Call it inside `_fetch_day()` with a try/except
5. Add the column to `schema.sql`
6. Delete `garmin.duckdb` if you need to rebuild the schema (or `ALTER TABLE` if you want to preserve data)

## Conventions
- All syncs are **read-only from Garmin, write to local DuckDB** — no posts or mutations to Garmin
- **No credentials in source** — env vars only via `.env`
- Upserts use `ON CONFLICT (pk) DO UPDATE SET` — reruns are safe and idempotent
- `_fetch_day()` wraps each endpoint call in try/except so one failure doesn't abort the whole day
- `signal.alarm(45)` timeout in `auth.py` prevents login hanging forever through exhausted strategies
- Garmin rate-limits mobile login per IP — if 429, wait 30-60 min or use VPN (US server)

## Credentials
- `GARMIN_EMAIL` — Garmin Connect account email
- `GARMIN_PASSWORD` — Garmin Connect account password
Both in `.env`. Session tokens cached in `.garth/` after first auth.

## DB schema

**health_days** — one row per calendar date
```
date                    DATE PRIMARY KEY
steps, step_goal        INTEGER
floors_up               FLOAT
distance_km             FLOAT
calories_total, calories_active, calories_bmr  INTEGER
hr_min, hr_max, rhr     INTEGER
stress_avg              INTEGER
bb_max, bb_min, bb_end  INTEGER          -- body battery (highest/lowest/most-recent)
moderate_activity_min, vigorous_activity_min  INTEGER
sleep_start, sleep_end  TIMESTAMP
sleep_score             INTEGER
sleep_qualifier         VARCHAR          -- 'GOOD', 'FAIR', 'POOR'
sleep_total_min, sleep_deep_min, sleep_light_min, sleep_rem_min, sleep_awake_min  FLOAT
sleep_spo2_avg, sleep_rr_avg  FLOAT
hrv_weekly_avg, hrv_last_night, hrv_baseline_low, hrv_baseline_high  FLOAT
hrv_status              VARCHAR
spo2_avg, spo2_min      FLOAT
rr_waking_avg           FLOAT
training_readiness_score  INTEGER        -- 0-100 composite score
training_readiness_level  VARCHAR        -- 'PRIME', 'GOOD', 'MODERATE', etc.
recovery_time_hours     INTEGER
endurance_score         INTEGER          -- raw Garmin scale (~3570–10560)
fitness_age             FLOAT            -- Garmin's computed fitness age
```

**health_activities** — one row per workout
```
activity_id             VARCHAR PRIMARY KEY
date                    DATE
start_time              TIMESTAMP
activity_type           VARCHAR          -- 'running', 'strength_training', 'boxing', etc.
duration_min            FLOAT
distance_km             FLOAT
avg_hr, max_hr          INTEGER
calories                INTEGER
training_effect_aerobic, training_effect_anaerobic  FLOAT
training_load           FLOAT
hr_zone1_min … hr_zone5_min  FLOAT
```

## API notes
- `garminconnect` tries 4 login strategies in sequence; mobile ones often 429 on first use
- `garth` (underlying auth library) is deprecated at module level — use `garth.http.Client` directly if needed
- `get_body_battery(date)` returns a list; the daily summary data is also in `get_stats()` under `bodyBatteryHighestValue` etc.
- `hrvWeeklyAverage` in `training_readiness` response is in 0.1ms units — divide by 10 for ms
- `max_metrics`, `lactate_threshold`, `body_composition` return empty/null for this account — skip
