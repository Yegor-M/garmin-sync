CREATE TABLE IF NOT EXISTS health_days (
    date                  DATE PRIMARY KEY,

    -- movement
    steps                 INTEGER,
    step_goal             INTEGER,
    floors_up             FLOAT,
    distance_km           FLOAT,

    -- calories
    calories_total        INTEGER,
    calories_active       INTEGER,
    calories_bmr          INTEGER,

    -- heart rate
    hr_min                INTEGER,
    hr_max                INTEGER,
    rhr                   INTEGER,

    -- stress & body battery
    stress_avg            INTEGER,
    bb_max                INTEGER,
    bb_min                INTEGER,
    bb_end                INTEGER,

    -- intensity minutes
    moderate_activity_min INTEGER,
    vigorous_activity_min INTEGER,

    -- sleep
    sleep_start           TIMESTAMP,
    sleep_end             TIMESTAMP,
    sleep_score           INTEGER,
    sleep_qualifier       VARCHAR,
    sleep_total_min       FLOAT,
    sleep_deep_min        FLOAT,
    sleep_light_min       FLOAT,
    sleep_rem_min         FLOAT,
    sleep_awake_min       FLOAT,
    sleep_spo2_avg        FLOAT,
    sleep_rr_avg          FLOAT,

    -- HRV
    hrv_weekly_avg        FLOAT,
    hrv_last_night        FLOAT,
    hrv_baseline_low      FLOAT,
    hrv_baseline_high     FLOAT,
    hrv_status            VARCHAR,

    -- SpO2 & respiration (daytime)
    spo2_avg              FLOAT,
    spo2_min              FLOAT,
    rr_waking_avg         FLOAT
);

CREATE TABLE IF NOT EXISTS health_activities (
    activity_id           VARCHAR PRIMARY KEY,
    date                  DATE,
    start_time            TIMESTAMP,
    activity_type         VARCHAR,
    duration_min          FLOAT,
    distance_km           FLOAT,
    avg_hr                INTEGER,
    max_hr                INTEGER,
    calories              INTEGER,
    training_effect_aerobic    FLOAT,
    training_effect_anaerobic  FLOAT,
    training_load         FLOAT,

    -- HR zones (seconds in each zone → minutes)
    hr_zone1_min          FLOAT,
    hr_zone2_min          FLOAT,
    hr_zone3_min          FLOAT,
    hr_zone4_min          FLOAT,
    hr_zone5_min          FLOAT
);
