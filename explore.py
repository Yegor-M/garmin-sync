"""
Exploration script — calls every interesting Garmin endpoint and dumps
raw JSON responses to data/raw/<endpoint>.json.

Run this once to see what your account actually returns before designing
the DuckDB schema.

Usage:
  GARMIN_EMAIL=x GARMIN_PASSWORD=y .venv/bin/python explore.py
  GARMIN_EMAIL=x GARMIN_PASSWORD=y .venv/bin/python explore.py --date 2025-03-10
"""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from auth import get_client

OUT = Path(__file__).parent / "data" / "raw"


def dump(name: str, data) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    size = path.stat().st_size
    print(f"  {name:40s} {size:>8,} bytes → {path.name}")


def explore(target_date: str) -> None:
    yesterday = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
    week_ago = (date.fromisoformat(target_date) - timedelta(days=7)).isoformat()

    print(f"\nConnecting...")
    api = get_client()
    print(f"Connected. Pulling data for {target_date}\n")

    endpoints = [
        # Daily summaries
        ("stats",               lambda: api.get_stats(target_date)),
        ("stats_and_body",      lambda: api.get_stats_and_body(target_date)),
        ("user_summary",        lambda: api.get_user_summary(target_date)),

        # Sleep
        ("sleep",               lambda: api.get_sleep_data(target_date)),

        # Heart rate
        ("heart_rates",         lambda: api.get_heart_rates(target_date)),
        ("resting_hr",          lambda: api.get_rhr_day(target_date)),

        # Stress & Body Battery
        ("stress",              lambda: api.get_stress_data(target_date)),
        ("body_battery",        lambda: api.get_body_battery(target_date)),

        # HRV
        ("hrv",                 lambda: api.get_hrv_data(target_date)),

        # Respiration & SpO2
        ("respiration",         lambda: api.get_respiration_data(target_date)),
        ("spo2",                lambda: api.get_spo2_data(target_date)),

        # Training
        ("training_status",     lambda: api.get_training_status(target_date)),
        ("training_readiness",  lambda: api.get_training_readiness(target_date)),

        # Activities (last 7 days for a richer sample)
        ("activities_week",     lambda: api.get_activities_by_date(week_ago, target_date)),

        # Personal records & predictions
        ("personal_records",    lambda: api.get_personal_record()),
        ("race_predictions",    lambda: api.get_race_predictions()),

        # Floors / intensity minutes
        ("floors",              lambda: api.get_floors(target_date)),
        ("intensity_minutes",   lambda: api.get_intensity_minutes_data(target_date)),

        # Hydration (if tracked)
        ("hydration",           lambda: api.get_hydration_data(target_date)),
    ]

    for name, fn in endpoints:
        try:
            data = fn()
            dump(name, data)
        except Exception as e:
            print(f"  {name:40s} SKIP — {e}")

    # Fetch one activity in detail if any exist
    try:
        activities = json.loads((OUT / "activities_week.json").read_text())
        if activities:
            activity_id = activities[0]["activityId"]
            dump("activity_detail_sample", api.get_activity_details(activity_id))
            dump("activity_hr_sample",     api.get_activity_hr_in_timezones(activity_id))
    except Exception as e:
        print(f"  activity_detail_sample                   SKIP — {e}")

    print(f"\nDone. Files in {OUT}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat(),
                        help="Target date (YYYY-MM-DD), default: today")
    args = parser.parse_args()
    explore(args.date)
