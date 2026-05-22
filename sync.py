"""
Daily sync: pulls Garmin Connect data → garmin.duckdb

Usage:
  python sync.py                     # yesterday + today (catches late-arriving data)
  python sync.py --date 2026-05-01   # specific date
  python sync.py --backfill 365      # last N days
"""

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from auth import get_client

load_dotenv()

DB_PATH = Path(__file__).parent / "garmin.duckdb"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _init_db(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA_PATH.read_text())


def _secs_to_min(v) -> float | None:
    return round(v / 60, 1) if v else None


def _ms_to_ts(ms) -> str | None:
    if not ms:
        return None
    return datetime.utcfromtimestamp(ms / 1000).isoformat()


# ---------------------------------------------------------------------------
# Extraction helpers — field names verified against garminconnect 0.3.x JSON.
# If a field comes back None after running explore.py, check the key name here.
# ---------------------------------------------------------------------------

def _extract_stats(s: dict) -> dict:
    return {
        "steps":                 s.get("totalSteps"),
        "step_goal":             s.get("dailyStepGoal"),
        "floors_up":             s.get("floorsAscended"),
        "distance_km":           round((s.get("totalDistanceMeters") or 0) / 1000, 3) or None,
        "calories_total":        s.get("totalKilocalories"),
        "calories_active":       s.get("activeKilocalories"),
        "calories_bmr":          s.get("bmrKilocalories"),
        "hr_min":                s.get("minHeartRate"),
        "hr_max":                s.get("maxHeartRate"),
        "rhr":                   s.get("restingHeartRate"),
        "stress_avg":            s.get("averageStressLevel"),
        "bb_max":                s.get("bodyBatteryHighestValue"),
        "bb_min":                s.get("bodyBatteryLowestValue"),
        "bb_end":                s.get("bodyBatteryMostRecentValue"),
        "moderate_activity_min": s.get("moderateIntensityMinutes"),
        "vigorous_activity_min": s.get("vigorousIntensityMinutes"),
        "spo2_avg":              s.get("averageSpo2"),
        "spo2_min":              s.get("lowestSpo2"),
        "rr_waking_avg":         s.get("avgWakingRespirationValue"),
    }


def _extract_sleep(data: dict) -> dict:
    dto = (data or {}).get("dailySleepDTO") or {}
    if not dto:
        return {}
    scores = (dto.get("sleepScores") or {}).get("overall") or {}
    deep  = dto.get("deepSleepSeconds") or 0
    light = dto.get("lightSleepSeconds") or 0
    rem   = dto.get("remSleepSeconds") or 0
    return {
        "sleep_start":     _ms_to_ts(dto.get("sleepStartTimestampGMT")),
        "sleep_end":       _ms_to_ts(dto.get("sleepEndTimestampGMT")),
        "sleep_score":     scores.get("value"),
        "sleep_qualifier": scores.get("qualifierKey"),
        "sleep_total_min": _secs_to_min(deep + light + rem),
        "sleep_deep_min":  _secs_to_min(deep),
        "sleep_light_min": _secs_to_min(light),
        "sleep_rem_min":   _secs_to_min(rem),
        "sleep_awake_min": _secs_to_min(dto.get("awakeSleepSeconds")),
        "sleep_spo2_avg":  dto.get("averageSpO2Value"),
        "sleep_rr_avg":    dto.get("averageRespirationValue"),
    }


def _extract_training_readiness(data) -> dict:
    item = (data or [{}])[0] if isinstance(data, list) else (data or {})
    hrv_weekly = item.get("hrvWeeklyAverage")
    return {
        "training_readiness_score": item.get("score"),
        "training_readiness_level": item.get("level"),
        "recovery_time_hours":      item.get("recoveryTime"),
        # hrvWeeklyAverage is in 0.1ms units — convert to ms
        # used as fallback when hrv endpoint weeklyAvg is null (during onboarding)
        "_hrv_weekly_from_readiness": round(hrv_weekly / 10, 1) if hrv_weekly else None,
    }


def _extract_endurance_score(data: dict) -> dict:
    dto = (data or {}).get("enduranceScoreDTO") or {}
    return {"endurance_score": dto.get("overallScore")}


def _extract_fitness_age(data: dict) -> dict:
    return {"fitness_age": (data or {}).get("fitnessAge")}


def _extract_hrv(data: dict) -> dict:
    summary = (data or {}).get("hrvSummary") or {}
    if not summary:
        return {}
    baseline = summary.get("baseline") or {}
    return {
        "hrv_weekly_avg":   summary.get("weeklyAvg"),
        "hrv_last_night":   summary.get("lastNightAvg"),
        "hrv_baseline_low": baseline.get("balancedLow"),
        "hrv_baseline_high": baseline.get("balancedUpper"),
        "hrv_status":       summary.get("status"),
    }


def _fetch_day(api, d: str) -> dict:
    row: dict = {"date": d}

    try:
        row.update(_extract_stats(api.get_stats(d) or {}))
    except Exception as e:
        print(f"    stats error: {e}")

    try:
        row.update(_extract_sleep(api.get_sleep_data(d)))
    except Exception as e:
        print(f"    sleep error: {e}")

    try:
        row.update(_extract_hrv(api.get_hrv_data(d)))
    except Exception as e:
        print(f"    hrv error: {e}")

    try:
        tr = _extract_training_readiness(api.get_training_readiness(d))
        hrv_fallback = tr.pop("_hrv_weekly_from_readiness", None)
        row.update(tr)
        # use readiness HRV weekly avg as fallback if hrv endpoint returned null
        if hrv_fallback and not row.get("hrv_weekly_avg"):
            row["hrv_weekly_avg"] = hrv_fallback
    except Exception as e:
        print(f"    training_readiness error: {e}")

    try:
        row.update(_extract_endurance_score(api.get_endurance_score(d, d)))
    except Exception as e:
        print(f"    endurance_score error: {e}")

    try:
        row.update(_extract_fitness_age(api.get_fitnessage_data(d)))
    except Exception as e:
        print(f"    fitness_age error: {e}")

    return row


def _upsert(con: duckdb.DuckDBPyConnection, table: str, pk: str, row: dict) -> None:
    cols    = ", ".join(row.keys())
    params  = ", ".join(["?" for _ in row])
    updates = ", ".join([f"{k} = excluded.{k}" for k in row if k != pk])
    con.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({params}) "
        f"ON CONFLICT ({pk}) DO UPDATE SET {updates}",
        list(row.values()),
    )


def _fetch_activities(api, start: str, end: str) -> list[dict]:
    rows = []
    try:
        activities = api.get_activities_by_date(start, end) or []
    except Exception as e:
        print(f"  activities list error: {e}")
        return rows

    for a in activities:
        activity_id = str(a.get("activityId") or "")
        if not activity_id:
            continue

        row = {
            "activity_id":               activity_id,
            "date":                      (a.get("startTimeLocal") or "")[:10],
            "start_time":                a.get("startTimeLocal"),
            "activity_type":             (a.get("activityType") or {}).get("typeKey"),
            "duration_min":              _secs_to_min(a.get("duration")),
            "distance_km":               round((a.get("distance") or 0) / 1000, 3) or None,
            "avg_hr":                    a.get("averageHR"),
            "max_hr":                    a.get("maxHR"),
            "calories":                  a.get("calories"),
            "training_effect_aerobic":   a.get("aerobicTrainingEffect"),
            "training_effect_anaerobic": a.get("anaerobicTrainingEffect"),
            "training_load":             a.get("activityTrainingLoad"),
            "hr_zone1_min": None, "hr_zone2_min": None, "hr_zone3_min": None,
            "hr_zone4_min": None, "hr_zone5_min": None,
        }

        try:
            details = api.get_activity_details(int(activity_id)) or {}
            zones = (details.get("summaryDTO") or {}).get("hrZones") or []
            for i, z in enumerate(zones[:5], 1):
                row[f"hr_zone{i}_min"] = _secs_to_min(z.get("secsInZone"))
        except Exception as e:
            print(f"    zones for {activity_id}: {e}")

        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Main sync
# ---------------------------------------------------------------------------

def sync_range(start: date, end: date) -> None:
    total = (end - start).days + 1
    print(f"Syncing {start} → {end} ({total} day{'s' if total != 1 else ''})")

    api = get_client()
    con = duckdb.connect(str(DB_PATH))
    _init_db(con)

    d = start
    i = 0
    while d <= end:
        i += 1
        ds = d.isoformat()
        print(f"  [{i}/{total}] {ds} ...", end=" ", flush=True)
        row = _fetch_day(api, ds)
        _upsert(con, "health_days", "date", row)
        print("ok")
        d += timedelta(days=1)

    print(f"\nFetching activities {start} → {end} ...", end=" ", flush=True)
    activity_rows = _fetch_activities(api, start.isoformat(), end.isoformat())
    for row in activity_rows:
        _upsert(con, "health_activities", "activity_id", row)
        print(f"\n  {row['date']} {row['activity_type']} ({row['duration_min']} min)", end="")

    print(f"\n\nDone. {total} days, {len(activity_rows)} activities → {DB_PATH}")
    con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--date",     help="Sync a specific date (YYYY-MM-DD)")
    group.add_argument("--backfill", type=int, metavar="DAYS", help="Sync last N days")
    args = parser.parse_args()

    today = date.today()

    if args.date:
        d = date.fromisoformat(args.date)
        sync_range(d, d)
    elif args.backfill:
        sync_range(today - timedelta(days=args.backfill), today)
    else:
        sync_range(today - timedelta(days=1), today)
