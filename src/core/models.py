import sqlite3
import os
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "apex_user.db")

# ==========================================
# PYDANTIC SCHEMAS (API Transfer)
# ==========================================
class UserProfile(BaseModel):
    name: str = "Athlete"
    age: int = 30
    weight_kg: float = 70.0
    max_hr: int = 190
    resting_hr: int = 50
    current_vdot: float = 40.0
    unit_preference: str = "km"
    avg_sleep_hours: float = 7.5
    life_stress_level: str = "low"

class TrainingPlan(BaseModel):
    id: Optional[int] = None
    goal: str
    target_date: str
    weekly_hours: float
    created_at: str

class PlannedWorkout(BaseModel):
    id: Optional[int] = None
    plan_id: int
    date: str
    sport: str
    workout_type: str # e.g. 'Interval', 'Long Run'
    planned_distance_meters: float
    planned_duration_seconds: float
    description: str
    completed: bool = False
    
class WorkoutLog(BaseModel):
    date: str
    sport: str
    distance_meters: float
    duration_seconds: float
    avg_hr: int
    rpe: int  # 1-10

class ManualWorkoutLog(BaseModel):
    date: str
    sport: str = "Run"
    distance_meters: float = 0
    duration_seconds: float = 0
    avg_hr: Optional[int] = None
    rpe: Optional[int] = 5
    notes: str = ""

class PlanConfirmRequest(BaseModel):
    plan_json: dict
    goal: str
    target_date: str
    weekly_hours: float
    start_date: str
    user_id: int = 1

class PlanAdjustRequest(BaseModel):
    plan_json: dict
    instruction: str
    plan_id: Optional[int] = None
    user_id: int = 1

class GoalLog(BaseModel):
    race_date: str
    target_distance_meters: float
    target_time_seconds: float

# ==========================================
# SQLITE INTERACTION
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # User Preferences
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT,
            age INTEGER,
            weight_kg REAL,
            max_hr INTEGER,
            resting_hr INTEGER,
            current_vdot REAL,
            unit_preference TEXT,
            avg_sleep_hours REAL,
            life_stress_level TEXT
        )
    ''')
    
    # Workouts
    c.execute('''
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            sport TEXT,
            distance_meters REAL,
            duration_seconds REAL,
            avg_hr INTEGER,
            rpe INTEGER,
            tss REAL,
            vdot_estimate REAL
        )
    ''')
    
    # Goals
    c.execute('''
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            race_date TEXT,
            target_distance_meters REAL,
            target_time_seconds REAL
        )
    ''')
    
    # Training Plans
    c.execute('''
        CREATE TABLE IF NOT EXISTS training_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            goal TEXT,
            target_date TEXT,
            weekly_hours REAL,
            created_at TEXT
        )
    ''')
    
    # Planned Workouts
    c.execute('''
        CREATE TABLE IF NOT EXISTS planned_workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER,
            date TEXT,
            sport TEXT,
            workout_type TEXT,
            planned_distance_meters REAL,
            planned_duration_seconds REAL,
            description TEXT,
            completed BOOLEAN DEFAULT 0,
            FOREIGN KEY(plan_id) REFERENCES training_plans(id)
        )
    ''')
    
    # Insert default user if not exists
    c.execute('SELECT COUNT(*) FROM users')
    if c.fetchone()[0] == 0:
        c.execute('''
            INSERT INTO users (id, name, age, weight_kg, max_hr, resting_hr, current_vdot, unit_preference, avg_sleep_hours, life_stress_level)
            VALUES (1, 'Athlete', 30, 70.0, 190, 50, 40.0, 'km', 7.5, 'low')
        ''')
        
    conn.commit()
    conn.close()

def get_user_profile(user_id: int = 1) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else {}

def update_user_vdot(new_vdot: float, user_id: int = 1):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET current_vdot = ? WHERE id = ?', (new_vdot, user_id))
    conn.commit()
    conn.close()

def log_workout(w: WorkoutLog, tss: float, vdot_estimate: float, user_id: int = 1):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO workouts (user_id, date, sport, distance_meters, duration_seconds, avg_hr, rpe, tss, vdot_estimate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, w.date, w.sport, w.distance_meters, w.duration_seconds, w.avg_hr, w.rpe, tss, vdot_estimate))
    conn.commit()
    conn.close()

def get_recent_workouts(user_id: int = 1, limit: int = 10) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM workouts WHERE user_id = ? ORDER BY date DESC LIMIT ?', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_training_plan(user_id: int, goal: str, target_date: str, weekly_hours: float) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO training_plans (user_id, goal, target_date, weekly_hours, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, goal, target_date, weekly_hours, datetime.now().isoformat()))
    plan_id = c.lastrowid
    conn.commit()
    conn.close()
    return plan_id

def add_planned_workout(plan_id: int, date: str, sport: str, workout_type: str, dist: float, dur: float, desc: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO planned_workouts (plan_id, date, sport, workout_type, planned_distance_meters, planned_duration_seconds, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (plan_id, date, sport, workout_type, dist, dur, desc))
    conn.commit()
    conn.close()

def confirm_plan(user_id: int, goal: str, target_date: str, weekly_hours: float, start_date: str, plan_json: dict) -> int:
    """Persist a previewed plan JSON to DB. Returns plan_id."""
    from datetime import timedelta
    plan_id = create_training_plan(user_id, goal, target_date, weekly_hours)
    sd = datetime.strptime(start_date, '%Y-%m-%d')
    days_map = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}
    start_weekday = sd.weekday()
    for week in plan_json.get("weeks", []):
        wn = week.get("week_number", 1) - 1
        for w in week.get("workouts", []):
            day_name = w.get("day", "Monday")
            day_offset = days_map.get(day_name, 0)
            target_day = sd + timedelta(days=(wn * 7) + day_offset - start_weekday)
            if target_day < sd:
                target_day += timedelta(days=7)
            add_planned_workout(
                plan_id=plan_id,
                date=target_day.strftime('%Y-%m-%d'),
                sport="Run",
                workout_type=w.get("type", "Workout"),
                dist=w.get("distance_km", 0) * 1000,
                dur=w.get("duration_min", 0) * 60,
                desc=w.get("description", "") + f" | Pace: {w.get('pace_min_per_km','N/A')}/km"
            )
    return plan_id

def get_latest_plan(user_id: int = 1) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM training_plans WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_planned_workouts(plan_id: int) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM planned_workouts WHERE plan_id = ? ORDER BY date ASC', (plan_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_planned_workout_by_id(workout_id: int) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM planned_workouts WHERE id = ?', (workout_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_planned_workout_execution(planned_workout_id: int, execution_data: str, execution_score: float, execution_feedback: str, completed: int,
                                      user_notes: str = None, llm_comment: str = None, skipped_reason: str = None,
                                      actual_distance_meters: float = None, actual_duration_seconds: float = None,
                                      actual_avg_hr: int = None, actual_rpe: int = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        UPDATE planned_workouts
        SET execution_data = ?,
            execution_score = ?,
            execution_feedback = ?,
            completed = ?,
            user_notes = COALESCE(?, user_notes),
            llm_comment = COALESCE(?, llm_comment),
            skipped_reason = COALESCE(?, skipped_reason),
            actual_distance_meters = COALESCE(?, actual_distance_meters),
            actual_duration_seconds = COALESCE(?, actual_duration_seconds),
            actual_avg_hr = COALESCE(?, actual_avg_hr),
            actual_rpe = COALESCE(?, actual_rpe)
        WHERE id = ?
    ''', (execution_data, execution_score, execution_feedback, completed,
          user_notes, llm_comment, skipped_reason,
          actual_distance_meters, actual_duration_seconds, actual_avg_hr, actual_rpe,
          planned_workout_id))
    conn.commit()
    conn.close()

def get_all_workouts(user_id: int = 1, source: str = None) -> list[dict]:
    """Get all workouts. If source is specified, filter by it."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if source:
        c.execute('SELECT * FROM workouts WHERE user_id = ? AND source = ? ORDER BY date ASC', (user_id, source))
    else:
        c.execute('SELECT * FROM workouts WHERE user_id = ? ORDER BY date ASC', (user_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_workout_streams(workout_id: int) -> Optional[dict]:
    """Return all stored stream arrays for a workout."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''SELECT hr_stream, time_stream, laps_json, distance_stream, altitude_stream,
                 velocity_stream, cadence_stream, watts_stream, grade_stream, moving_stream,
                 splits_json, best_efforts_json, segment_efforts_json
              FROM workouts WHERE id = ?''', (workout_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def log_manual_workout(w, tss: float, vdot_estimate: float, user_id: int = 1):
    """Log a manual workout with source='manual'."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO workouts (user_id, date, sport, distance_meters, duration_seconds, avg_hr, rpe, tss, vdot_estimate, source, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', ?)
    ''', (user_id, w.date, w.sport, w.distance_meters, w.duration_seconds, w.avg_hr, w.rpe, tss, vdot_estimate, w.notes))
    conn.commit()
    conn.close()

def update_user_pbs(user_id: int = 1, **kwargs):
    """Update user PBs and profile fields."""
    allowed = {'pb_5k_seconds', 'pb_10k_seconds', 'pb_hm_seconds', 'pb_marathon_seconds',
               'pb_other_text', 'current_weekly_km', 'experience_level', 'injury_notes'}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    set_clause = ', '.join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [user_id]
    c.execute(f'UPDATE users SET {set_clause} WHERE id = ?', values)
    conn.commit()
    conn.close()

def save_plan_chat_message(plan_id: Optional[int], role: str, content: str, mode: str = 'plan'):
    """Save a message to plan chat history."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO plan_chat_history (plan_id, role, content, mode) VALUES (?, ?, ?, ?)',
              (plan_id, role, content, mode))
    conn.commit()
    conn.close()

def get_plan_chat_history(plan_id: int = None, mode: str = None) -> list[dict]:
    """Get plan chat history, optionally filtered."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    query = 'SELECT * FROM plan_chat_history WHERE 1=1'
    params = []
    if plan_id is not None:
        query += ' AND plan_id = ?'
        params.append(plan_id)
    if mode:
        query += ' AND mode = ?'
        params.append(mode)
    query += ' ORDER BY created_at ASC'
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ==========================================
# STRAVA INTEGRATION HELPERS
# ==========================================
def save_strava_tokens(strava_athlete_id: int, access_token: str, refresh_token: str, expires_at: int, athlete_firstname: str = "", user_id: int = 1):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        UPDATE users SET
            strava_athlete_id = ?, strava_access_token = ?, strava_refresh_token = ?,
            strava_token_expires_at = ?, strava_connected = 1, name = COALESCE(?, name)
        WHERE id = ?
    ''', (strava_athlete_id, access_token, refresh_token, expires_at, athlete_firstname, user_id))
    conn.commit()
    conn.close()

def get_strava_tokens(user_id: int = 1) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT strava_access_token, strava_refresh_token, strava_token_expires_at, strava_connected FROM users WHERE id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row and row['strava_connected']:
        return dict(row)
    return None

def update_strava_tokens(access_token: str, refresh_token: str, expires_at: int, user_id: int = 1):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET strava_access_token = ?, strava_refresh_token = ?, strava_token_expires_at = ? WHERE id = ?',
              (access_token, refresh_token, expires_at, user_id))
    conn.commit()
    conn.close()

def delete_strava_tokens(user_id: int = 1):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET strava_connected = 0, strava_access_token = NULL, strava_refresh_token = NULL WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()

def upsert_workout(data: dict, user_id: int = 1):
    """Insert or skip a workout (by strava_activity_id uniqueness). V4: Extended fields."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Check if already exists
    if data.get('strava_activity_id'):
        c.execute('SELECT id FROM workouts WHERE strava_activity_id = ?', (data['strava_activity_id'],))
        if c.fetchone():
            conn.close()
            return  # Skip duplicate
    c.execute('''
        INSERT INTO workouts (user_id, date, sport, sport_type, sport_category, distance_meters, duration_seconds,
            avg_hr, max_hr, avg_cadence, rpe, tss, vdot_estimate, strava_activity_id, source, name, elevation_gain_m,
            hr_stream, time_stream, laps_json,
            avg_watts, max_watts, np_watts, kilojoules, avg_temp_c, suffer_score,
            splits_json, best_efforts_json, segment_efforts_json, achievement_count, pr_count,
            distance_stream, altitude_stream, velocity_stream, cadence_stream, watts_stream, grade_stream, moving_stream)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, data.get('date'), data.get('sport_type', 'run'), data.get('sport_type', 'run'), data.get('sport_category', 'run'),
          data.get('distance', 0) * 1000 if data.get('distance') is not None else 0, data.get('duration', 0),
          data.get('avg_hr'), data.get('max_hr'), data.get('avg_cadence'),
          data.get('rpe', 5), data.get('tss', 0), data.get('vdot', 0),
          data.get('strava_activity_id'), data.get('source', 'manual'),
          data.get('name', ''), data.get('elevation_gain_m', 0),
          data.get('hr_stream'), data.get('time_stream'), data.get('laps_json'),
          # V4 extended fields
          data.get('avg_watts'), data.get('max_watts'), data.get('np_watts'),
          data.get('kilojoules'), data.get('avg_temp_c'), data.get('suffer_score'),
          data.get('splits_json'), data.get('best_efforts_json'), data.get('segment_efforts_json'),
          data.get('achievement_count'), data.get('pr_count'),
          data.get('distance_stream'), data.get('altitude_stream'), data.get('velocity_stream'),
          data.get('cadence_stream'), data.get('watts_stream'), data.get('grade_stream'), data.get('moving_stream')))
    conn.commit()
    conn.close()

def delete_workout_by_strava_id(strava_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM workouts WHERE strava_activity_id = ?', (strava_id,))
    conn.commit()
    conn.close()

# Initialize on import
init_db()

