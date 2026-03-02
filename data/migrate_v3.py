import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "apex_user.db")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

migrations = [
    # ── Workouts table additions ──
    "ALTER TABLE workouts ADD COLUMN sport_type TEXT DEFAULT 'Run'",
    "ALTER TABLE workouts ADD COLUMN sport_category TEXT DEFAULT 'cardio'",
    # cardio | strength | flexibility | crosstraining | water | winter | other
    "ALTER TABLE workouts ADD COLUMN strava_activity_id INTEGER",
    "ALTER TABLE workouts ADD COLUMN source TEXT DEFAULT 'manual'",
    "ALTER TABLE workouts ADD COLUMN name TEXT",
    "ALTER TABLE workouts ADD COLUMN max_hr INTEGER",
    "ALTER TABLE workouts ADD COLUMN avg_cadence INTEGER",
    "ALTER TABLE workouts ADD COLUMN elevation_gain_m REAL DEFAULT 0",
    "ALTER TABLE workouts ADD COLUMN notes TEXT",
    "ALTER TABLE workouts ADD COLUMN hr_stream TEXT",   # JSON array of HR values
    "ALTER TABLE workouts ADD COLUMN time_stream TEXT", # JSON array of timestamps
    "ALTER TABLE workouts ADD COLUMN laps_json TEXT",   # JSON array of lap data
    "ALTER TABLE workouts ADD COLUMN perceived_effort INTEGER",
    "ALTER TABLE workouts ADD COLUMN workout_execution_score REAL",  # 1-10 AI score
    "ALTER TABLE workouts ADD COLUMN execution_notes TEXT",          # AI feedback

    # ── planned_workouts table additions ──
    "ALTER TABLE planned_workouts ADD COLUMN execution_data TEXT",  # JSON: user-entered splits
    "ALTER TABLE planned_workouts ADD COLUMN execution_score REAL", # 1-10
    "ALTER TABLE planned_workouts ADD COLUMN execution_feedback TEXT",
    "ALTER TABLE planned_workouts ADD COLUMN completed INTEGER DEFAULT 0",

    # ── users table additions ──
    "ALTER TABLE users ADD COLUMN strava_athlete_id INTEGER",
    "ALTER TABLE users ADD COLUMN strava_access_token TEXT",
    "ALTER TABLE users ADD COLUMN strava_refresh_token TEXT",
    "ALTER TABLE users ADD COLUMN strava_token_expires_at INTEGER",
    "ALTER TABLE users ADD COLUMN strava_connected INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN ftp_watts REAL",
    "ALTER TABLE users ADD COLUMN lthr REAL",
    "ALTER TABLE users ADD COLUMN preferred_sport TEXT DEFAULT 'Run'",
    "ALTER TABLE users ADD COLUMN date_of_birth TEXT",
    "ALTER TABLE users ADD COLUMN weight_kg REAL",
]

for sql in migrations:
    try:
        cur.execute(sql)
        print(f"✅ {sql[:70]}...")
    except sqlite3.OperationalError as e:
        print(f"⚠️  Skip (exists): {e}")

conn.commit()
conn.close()
print("\n✅ Migration V3 complete.")
