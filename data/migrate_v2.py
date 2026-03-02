"""
Database Migration Script v2 — Run once to add all new columns.
Safe to re-run: uses ALTER TABLE only and catches "already exists" errors.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "apex_user.db")

def run_migration():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    migrations = [
        # Strava integration columns
        "ALTER TABLE users ADD COLUMN strava_athlete_id INTEGER",
        "ALTER TABLE users ADD COLUMN strava_access_token TEXT",
        "ALTER TABLE users ADD COLUMN strava_refresh_token TEXT",
        "ALTER TABLE users ADD COLUMN strava_token_expires_at INTEGER",
        "ALTER TABLE users ADD COLUMN strava_connected INTEGER DEFAULT 0",
        # Enhanced user profile
        "ALTER TABLE users ADD COLUMN ftp_watts REAL",
        "ALTER TABLE users ADD COLUMN lthr REAL",
        "ALTER TABLE users ADD COLUMN preferred_sport TEXT DEFAULT 'run'",
        # Enhanced workout columns
        "ALTER TABLE workouts ADD COLUMN strava_activity_id INTEGER",
        "ALTER TABLE workouts ADD COLUMN source TEXT DEFAULT 'manual'",
        "ALTER TABLE workouts ADD COLUMN sport_type TEXT DEFAULT 'run'",
        "ALTER TABLE workouts ADD COLUMN max_hr INTEGER",
        "ALTER TABLE workouts ADD COLUMN avg_cadence INTEGER",
        "ALTER TABLE workouts ADD COLUMN name TEXT",
        "ALTER TABLE workouts ADD COLUMN notes TEXT",
        "ALTER TABLE workouts ADD COLUMN elevation_gain_m REAL DEFAULT 0",
    ]

    for sql in migrations:
        try:
            cursor.execute(sql)
            print(f"✅ {sql[:70]}...")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"⏭️  Skipped (exists): {sql.split('ADD COLUMN')[1].strip().split()[0]}")
            else:
                print(f"⚠️  Error: {e}")

    conn.commit()
    conn.close()
    print("\n🏁 Migration complete.")

if __name__ == "__main__":
    run_migration()
