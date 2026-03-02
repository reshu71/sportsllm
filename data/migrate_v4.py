"""
APEX V4 Database Migration
Adds new columns for extended Strava streams, PBs, splits, plan chat history,
and enhanced execution tracking.
Run once: python3 data/migrate_v4.py
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "apex_user.db")

WORKOUTS_COLUMNS = [
    ("avg_watts",              "REAL"),
    ("max_watts",              "REAL"),
    ("np_watts",               "REAL"),
    ("kilojoules",             "REAL"),
    ("avg_temp_c",             "REAL"),
    ("suffer_score",           "INTEGER"),
    ("splits_json",            "TEXT"),
    ("best_efforts_json",      "TEXT"),
    ("segment_efforts_json",   "TEXT"),
    ("achievement_count",      "INTEGER"),
    ("pr_count",               "INTEGER"),
    ("distance_stream",        "TEXT"),
    ("altitude_stream",        "TEXT"),
    ("velocity_stream",        "TEXT"),
    ("cadence_stream",         "TEXT"),
    ("watts_stream",           "TEXT"),
    ("grade_stream",           "TEXT"),
    ("moving_stream",          "TEXT"),
]

USERS_COLUMNS = [
    ("pb_5k_seconds",          "INTEGER"),
    ("pb_10k_seconds",         "INTEGER"),
    ("pb_hm_seconds",          "INTEGER"),
    ("pb_marathon_seconds",    "INTEGER"),
    ("pb_other_text",          "TEXT"),
    ("current_weekly_km",      "REAL"),
    ("experience_level",       "TEXT"),
    ("injury_notes",           "TEXT"),
]

PLANNED_WORKOUTS_COLUMNS = [
    ("user_notes",                 "TEXT"),
    ("llm_comment",                "TEXT"),
    ("skipped_reason",             "TEXT"),
    ("actual_distance_meters",     "REAL"),
    ("actual_duration_seconds",    "REAL"),
    ("actual_avg_hr",              "INTEGER"),
    ("actual_rpe",                 "INTEGER"),
    ("linked_workout_id",          "INTEGER"),
]

CREATE_PLAN_CHAT = """
CREATE TABLE IF NOT EXISTS plan_chat_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id     INTEGER,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    mode        TEXT DEFAULT 'plan',
    created_at  TEXT DEFAULT (datetime('now'))
);
"""

def add_columns(conn, table, columns):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    added = 0
    for col_name, col_type in columns:
        if col_name not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
            print(f"  + {table}.{col_name} ({col_type})")
            added += 1
        else:
            print(f"  ~ {table}.{col_name} already exists")
    return added

def run():
    print(f"Connecting to: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    print("\n[workouts]")
    add_columns(conn, "workouts", WORKOUTS_COLUMNS)
    print("\n[users]")
    add_columns(conn, "users", USERS_COLUMNS)
    print("\n[planned_workouts]")
    add_columns(conn, "planned_workouts", PLANNED_WORKOUTS_COLUMNS)
    print("\n[plan_chat_history]")
    conn.execute(CREATE_PLAN_CHAT)
    print("  + Created plan_chat_history table (or already exists)")
    conn.commit()
    conn.close()
    print("\n✅ V4 migration complete.")

if __name__ == "__main__":
    run()
