"""
Daily sync — pulls Garmin data and writes to garmin.duckdb.

Schema is intentionally left as TODO until explore.py has been run
and we've seen what the API actually returns.

Usage:
  GARMIN_EMAIL=x GARMIN_PASSWORD=y .venv/bin/python sync.py
  GARMIN_EMAIL=x GARMIN_PASSWORD=y .venv/bin/python sync.py --date 2025-03-10
  GARMIN_EMAIL=x GARMIN_PASSWORD=y .venv/bin/python sync.py --backfill 365
"""

# TODO: implement after explore.py reveals actual data shapes
# Planned tables:
#   health_days       — one row per date (sleep, HRV, stress, body battery, resting HR, steps)
#   health_activities — one row per workout (type, duration, HR zones, training load)
