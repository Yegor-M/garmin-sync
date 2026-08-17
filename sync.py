"""
Daily sync: pulls Garmin Connect data → garmin.duckdb

Usage:
  python sync.py                     # yesterday + today (catches late-arriving data)
  python sync.py --date 2026-05-01   # specific date
  python sync.py --backfill 365      # last N days
  python sync.py --status            # show DB summary without syncing
"""

import argparse
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from auth import get_client

load_dotenv()

DB_PATH = Path(__file__).parent / "garmin.duckdb"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Show one line per day for short syncs; milestone % updates for long ones
VERBOSE_THRESHOLD = 14


def _call(fn, retries: int = 2, wait: int = 5):
    """Call fn(), retrying up to `retries` times on 429 / rate-limit errors."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            msg = str(e).lower()
            if ("429" in msg or "too many" in msg) and attempt < retries:
                time.sleep(wait * (attempt + 1))
                continue
            raise


def _init_db(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA_PATH.read_text())


def _secs_to_min(v) -> float | None:
    return round(v / 60, 1) if v else None


def _ms_to_ts(ms) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None).isoformat()


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


def _extract_hrv(data: dict) -> dict:
    summary = (data or {}).get("hrvSummary") or {}
    if not summary:
        return {}
    baseline = summary.get("baseline") or {}
    return {
        "hrv_weekly_avg":    summary.get("weeklyAvg"),
        "hrv_last_night":    summary.get("lastNightAvg"),
        "hrv_baseline_low":  baseline.get("balancedLow"),
        "hrv_baseline_high": baseline.get("balancedUpper"),
        "hrv_status":        summary.get("status"),
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


def _extract_training_status(data: dict) -> dict:
    mts = (data or {}).get("mostRecentTrainingStatus") or {}
    device_data = mts.get("latestTrainingStatusData") or {}
    entry = next(
        (v for v in device_data.values() if v.get("primaryTrainingDevice")),
        next(iter(device_data.values()), {}) if device_data else {},
    )
    acwr = entry.get("acuteTrainingLoadDTO") or {}

    lb_map = ((data or {}).get("mostRecentTrainingLoadBalance") or {}).get(
        "metricsTrainingLoadBalanceDTOMap"
    ) or {}
    lb_entry = next(
        (v for v in lb_map.values() if v.get("primaryTrainingDevice")),
        next(iter(lb_map.values()), {}) if lb_map else {},
    )

    return {
        "training_status_phrase": entry.get("trainingStatusFeedbackPhrase"),
        "training_load_balance":  lb_entry.get("trainingBalanceFeedbackPhrase"),
        "acwr_status":            acwr.get("acwrStatus"),
    }


def _fetch_day(api, d: str) -> tuple[dict, list[str]]:
    """Returns (row_dict, list_of_error_strings). Never raises."""
    row: dict = {"date": d}
    errors: list[str] = []

    def try_update(name: str, extract_fn):
        try:
            row.update(_call(extract_fn))
        except Exception as e:
            errors.append(f"{name}: {e}")

    try_update("stats",    lambda: _extract_stats(api.get_stats(d) or {}))
    try_update("sleep",    lambda: _extract_sleep(api.get_sleep_data(d)))
    try_update("hrv",      lambda: _extract_hrv(api.get_hrv_data(d)))

    try:
        tr = _extract_training_readiness(_call(lambda: api.get_training_readiness(d)))
        hrv_fallback = tr.pop("_hrv_weekly_from_readiness", None)
        row.update(tr)
        if hrv_fallback and not row.get("hrv_weekly_avg"):
            row["hrv_weekly_avg"] = hrv_fallback
    except Exception as e:
        errors.append(f"training_readiness: {e}")

    try_update("endurance",        lambda: _extract_endurance_score(api.get_endurance_score(d, d)))
    try_update("fitness_age",      lambda: _extract_fitness_age(api.get_fitnessage_data(d)))
    try_update("training_status",  lambda: _extract_training_status(api.get_training_status(d)))

    return row, errors


def _upsert(con: duckdb.DuckDBPyConnection, table: str, pk: str, row: dict) -> None:
    cols    = ", ".join(row.keys())
    params  = ", ".join(["?" for _ in row])
    updates = ", ".join([f"{k} = excluded.{k}" for k in row if k != pk])
    con.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({params}) "
        f"ON CONFLICT ({pk}) DO UPDATE SET {updates}",
        list(row.values()),
    )


def _fetch_activities(api, start: str, end: str) -> tuple[list[dict], list[str]]:
    """Returns (rows, errors). Never raises."""
    rows: list[dict] = []
    errors: list[str] = []

    try:
        activities = api.get_activities_by_date(start, end) or []
    except Exception as e:
        return rows, [f"activities list: {e}"]

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
            "avg_pace_min_km":           round(1000 / a["averageSpeed"] / 60, 2) if a.get("averageSpeed") else None,
            "hr_zone1_min": None, "hr_zone2_min": None, "hr_zone3_min": None,
            "hr_zone4_min": None, "hr_zone5_min": None,
        }

        try:
            details = _call(lambda: api.get_activity_details(int(activity_id))) or {}
            zones = (details.get("summaryDTO") or {}).get("hrZones") or []
            for i, z in enumerate(zones[:5], 1):
                row[f"hr_zone{i}_min"] = _secs_to_min(z.get("secsInZone"))
        except Exception as e:
            errors.append(f"zones {activity_id}: {e}")

        rows.append(row)

    return rows, errors


# ---------------------------------------------------------------------------
# Main sync
# ---------------------------------------------------------------------------

def sync_range(start: date, end: date) -> None:
    total = (end - start).days + 1
    verbose = total <= VERBOSE_THRESHOLD
    milestone = max(1, round(total / 10))

    t0 = time.monotonic()
    print(f"Syncing {start} → {end} ({total} day{'s' if total != 1 else ''})")

    api = get_client()
    con = duckdb.connect(str(DB_PATH))
    _init_db(con)

    all_errors: list[str] = []
    partial_days = 0

    d = start
    i = 0
    while d <= end:
        i += 1
        ds = d.isoformat()
        row, errors = _fetch_day(api, ds)
        _upsert(con, "health_days", "date", row)

        if errors:
            partial_days += 1
            all_errors.extend([f"  {ds} {e}" for e in errors])

        if verbose:
            status = f"partial ({', '.join(e.split(':')[0] for e in errors)})" if errors else "ok"
            print(f"  [{i}/{total}] {ds} {status}")
        elif i % milestone == 0 or i == total:
            pct = round(i / total * 100)
            status = f"+{len([e for e in all_errors if ds in e])} errors" if errors else "ok"
            print(f"  [{i}/{total}] {ds} ({pct}%) {status}")

        d += timedelta(days=1)

    # Activities
    print(f"Activities {start} → {end} ...", end=" ", flush=True)
    activity_rows, act_errors = _fetch_activities(api, start.isoformat(), end.isoformat())
    for row in activity_rows:
        _upsert(con, "health_activities", "activity_id", row)
    all_errors.extend([f"  {e}" for e in act_errors])
    print(f"{len(activity_rows)} synced")

    # Summary
    elapsed = time.monotonic() - t0
    error_count = len(all_errors)
    print(f"\nDone — {total} days ({partial_days} partial), {len(activity_rows)} activities, "
          f"{error_count} error{'s' if error_count != 1 else ''} [{elapsed:.1f}s]")

    if all_errors:
        print("\nErrors:")
        for e in all_errors:
            print(e)

    con.close()


def show_status() -> None:
    if not DB_PATH.exists():
        print("garmin.duckdb not found — run sync.py to create it")
        return
    con = duckdb.connect(str(DB_PATH), read_only=True)
    days_row = con.execute(
        "SELECT COUNT(*), MIN(date)::VARCHAR, MAX(date)::VARCHAR FROM health_days"
    ).fetchone()
    act_count = con.execute("SELECT COUNT(*) FROM health_activities").fetchone()[0]
    con.close()

    session = (Path(__file__).parent / ".garth" / "garmin_tokens.json").exists()
    size_kb = DB_PATH.stat().st_size // 1024

    count, first, last = days_row
    print(f"Database:    {DB_PATH} ({size_kb} KB)")
    print(f"health_days: {count} rows  {first} → {last}")
    print(f"activities:  {act_count} rows")
    print(f"Session:     {'cached (.garth/)' if session else 'not found — run auth.py'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--date",     help="Sync a specific date (YYYY-MM-DD)")
    group.add_argument("--backfill", type=int, metavar="DAYS", help="Sync last N days")
    group.add_argument("--status",   action="store_true",      help="Show DB summary")
    args = parser.parse_args()

    today = date.today()

    if args.status:
        show_status()
    elif args.date:
        d = date.fromisoformat(args.date)
        sync_range(d, d)
    elif args.backfill:
        sync_range(today - timedelta(days=args.backfill), today)
    else:
        sync_range(today - timedelta(days=1), today)
