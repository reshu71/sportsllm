import os
import json
import time
import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

import openai
import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import CrossEncoder

import src.core.models as db_models
from src.services.sports_science import (
    calculate_vdot, calculate_tss, predict_race_time, predict_all_race_times,
    compute_pmc_series, compute_ramp_rate, calculate_hr_zones, classify_workout_zone,
    format_time, classify_sport, sport_type_to_label
)
from src.services.planner import generate_plan_streaming

load_dotenv()

# ==========================================
# CONFIGURATION
# ==========================================
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "endurance_db")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "endurance_knowledge_base")
EMBED_MODEL = "text-embedding-3-small"
RERANKER_MODEL = "BAAI/bge-reranker-base"
CHAT_MODEL = "gpt-4o-mini"
COARSE_K = 8
FINAL_K = 3

# Strava
STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
STRAVA_VERIFY_TOKEN = os.getenv("STRAVA_VERIFY_TOKEN", "apex_verify")

if not OPENAI_KEY:
    print("WARNING: OPENAI_API_KEY not set in environment.")

# ==========================================
# SIMPLE RESPONSE CACHE
# ==========================================
_cache: dict = {}
def cached(key: str, ttl: int = 300):
    """Simple TTL cache decorator."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            now = time.time()
            if key in _cache and now - _cache[key]['ts'] < ttl:
                return _cache[key]['data']
            result = func(*args, **kwargs)
            _cache[key] = {'data': result, 'ts': now}
            return result
        return wrapper
    return decorator

# ==========================================
# INITIALIZATION
# ==========================================
print("🧠 Connecting to ChromaDB at", DB_PATH)
try:
    oai_client = openai.OpenAI(api_key=OPENAI_KEY)
    chroma = chromadb.PersistentClient(path=DB_PATH)
    openai_ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=OPENAI_KEY, model_name=EMBED_MODEL
    )
    try:
        collection = chroma.get_collection(name=COLLECTION_NAME, embedding_function=openai_ef)
    except Exception:
        COLLECTION_NAME = "endurance_v2"
        collection = chroma.get_collection(name=COLLECTION_NAME, embedding_function=openai_ef)
    print(f"✅ Loaded ChromaDB collection '{COLLECTION_NAME}' with {collection.count():,} chunks")
    print(f"⏳ Loading reranker ({RERANKER_MODEL})...")
    reranker = CrossEncoder(RERANKER_MODEL)
    print("✅ Ready")
except Exception as e:
    print(f"⚠️ Error initializing models or DB: {e}")
    oai_client, collection, reranker = None, None, None

# ==========================================
# RAG LOGIC
# ==========================================
SPORT_KW = {
    "running":   ["run", "jog", "marathon", "ultra", "5k", "10k", "trail", "pace"],
    "cycling":   ["cycl", "bike", "watt", "ftp", "velo"],
    "triathlon": ["tri", "ironman", "70.3", "brick"],
    "swimming":  ["swim", "pool", "open water"],
    "rowing":    ["row", "erg"],
}

def detect_sport(query: str):
    q = query.lower()
    return next((s for s, kws in SPORT_KW.items() if any(k in q for k in kws)), None)

def retrieve(query: str, sport: str | None) -> list[dict]:
    if not collection or not reranker: return []
    kwargs = dict(query_texts=[query], n_results=COARSE_K, include=["documents", "metadatas", "distances"])
    if sport:
        kwargs["where"] = {"sport_type": {"$in": [sport, "multi", "other"]}}
    try:
        res = collection.query(**kwargs)
    except Exception:
        kwargs.pop("where", None)
        try:
            res = collection.query(**kwargs)
        except Exception:
            return []
    docs  = res["documents"][0]
    metas = res["metadatas"][0]
    if not docs:
        return []
    scores = reranker.predict([[query, d] for d in docs])
    ranked = sorted(zip(scores, docs, metas), key=lambda x: x[0], reverse=True)
    return [{"content": doc, "metadata": meta, "score": float(score)} for score, doc, meta in ranked[:FINAL_K]]

SYSTEM_PROMPT = """\
You are APEX — an elite AI endurance coach and sports scientist with expertise in
triathlon, marathon, cycling, swimming, exercise physiology, sports nutrition, and training methodology.

Your goal is to act as a highly personalized, predictive coaching engine (like a smart Jack Daniels VDOT or Kaizen). 
You hold the athlete's current state and workout history in context. 

Rules:
- Give highly personalized advice using the user's current VDOT, max HR, and recent Training Stress Score (TSS).
- Suggest precise paces or workload adjustments based on their fitness.
- Answer using the provided RAG context chunks.
- Cite source type (scientific study vs workout log) where relevant.
- Give practical, actionable advice.
- Use markdown formatting for clarity.
"""

# ==========================================
# FASTAPI APP
# ==========================================
app = FastAPI(title="APEX Endurance Coach API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]

class PlanRequest(BaseModel):
    goal: str
    target_date: str
    weekly_hours: float
    start_date: str
    user_id: int = 1

# ==========================================
# ENDPOINTS: USER METRICS
# ==========================================
@app.get("/api/profile")
def get_profile():
    profile = db_models.get_user_profile(user_id=1)
    recent = db_models.get_recent_workouts(user_id=1, limit=5)
    return {"profile": profile, "recent_workouts": recent}

@app.post("/api/workouts")
def add_workout(w: db_models.WorkoutLog):
    prof = db_models.get_user_profile(user_id=1)
    tss = calculate_tss(w.duration_seconds, w.avg_hr, prof.get("max_hr", 190), prof.get("resting_hr", 50))
    vdot_est = calculate_vdot(w.distance_meters, w.duration_seconds)
    db_models.log_workout(w, tss, vdot_est, user_id=1)
    if w.rpe >= 8 and vdot_est > prof.get("current_vdot", 0):
        db_models.update_user_vdot(vdot_est, user_id=1)
    return {"status": "success", "tss": tss, "vdot_estimate": vdot_est}

@app.get("/api/workouts")
def get_workouts(period: str = Query("30"), user_id: int = 1):
    from datetime import datetime, timedelta
    conn = sqlite3.connect(db_models.DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        days = int(period)
    except ValueError:
        days = 30
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    c.execute('SELECT * FROM workouts WHERE user_id = ? AND date >= ? ORDER BY date DESC', (user_id, cutoff))
    rows = c.fetchall()
    conn.close()
    return {"workouts": [dict(r) for r in rows]}

# ==========================================
# ENDPOINTS: ANALYTICS (PMC, ZONES, STREAKS)
# ==========================================
@app.get("/api/analytics/pmc")
def get_pmc():
    """Performance Management Chart data — CTL, ATL, TSB series."""
    workouts = db_models.get_all_workouts(user_id=1)
    tss_series = [{'date': w['date'], 'tss': w['tss']} for w in workouts if w.get('tss')]
    pmc = compute_pmc_series(tss_series)
    if pmc:
        ramp = compute_ramp_rate(pmc)
        latest = pmc[-1]
        form_label = "Fresh" if latest['tsb'] > 10 else "Optimal" if latest['tsb'] >= -30 else "High Risk"
        return {"series": pmc, "ramp_rate": ramp, "form": form_label, "latest": latest}
    return {"series": [], "ramp_rate": 0, "form": "No Data", "latest": {}}

@app.get("/api/analytics/zones")
def get_hr_zones():
    """Heart Rate Zones + zone distribution from recent workouts."""
    prof = db_models.get_user_profile(user_id=1)
    max_hr = prof.get("max_hr", 190)
    resting_hr = prof.get("resting_hr", 50)
    zones = calculate_hr_zones(max_hr, resting_hr)

    # Zone distribution from workouts
    workouts = db_models.get_all_workouts(user_id=1)
    zone_counts = {z: 0 for z in zones}
    for w in workouts:
        if w.get("avg_hr"):
            z = classify_workout_zone(w["avg_hr"], max_hr, resting_hr)
            if z in zone_counts:
                zone_counts[z] += 1
    total = sum(zone_counts.values()) or 1
    zone_pcts = {z: round(c / total * 100, 1) for z, c in zone_counts.items()}

    return {"zones": {z: {"min": lo, "max": hi} for z, (lo, hi) in zones.items()},
            "distribution": zone_pcts, "total_workouts": total}

@app.get("/api/stats/streaks")
def get_streaks():
    """Workout streak, totals, and weekly load."""
    workouts = db_models.get_all_workouts(user_id=1)
    dates = sorted(set(w['date'] for w in workouts), reverse=True)
    # Current streak
    current_streak = 0
    check = datetime.today()
    for date_str in dates:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        diff = (check - d).days
        if diff <= 1:
            current_streak += 1
            check = d
        else:
            break
    # Longest streak
    longest = 0
    streak = 1
    for i in range(1, len(dates)):
        d1 = datetime.strptime(dates[i-1], '%Y-%m-%d')
        d2 = datetime.strptime(dates[i], '%Y-%m-%d')
        if (d1 - d2).days == 1:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 1
    # Weekly TSS
    week_ago = (datetime.today() - timedelta(days=7)).strftime('%Y-%m-%d')
    weekly_tss = sum(w.get('tss', 0) for w in workouts if w['date'] >= week_ago)
    return {
        "current_streak": current_streak,
        "longest_streak": max(longest, current_streak),
        "total_workouts": len(workouts),
        "weekly_tss": round(weekly_tss, 1)
    }

@app.post("/api/predict/races")
def predict_races(body: dict):
    """Multi-distance race predictions from a known result."""
    dist_km = body.get("distance_km", 5)
    time_sec = body.get("time_seconds", 1200)
    predictions = predict_all_race_times(dist_km, time_sec)
    vdot = calculate_vdot(dist_km * 1000, time_sec)
    return {"predictions": predictions, "vdot": vdot}

@app.get("/api/analytics/heatmap")
def get_heatmap():
    """52-week workout heatmap data."""
    workouts = db_models.get_all_workouts(user_id=1)
    # Build date->tss map for last 365 days
    today = datetime.today()
    start = today - timedelta(days=364)
    tss_map = {}
    for w in workouts:
        d = w.get('date', '')
        if d >= start.strftime('%Y-%m-%d'):
            tss_map[d] = tss_map.get(d, 0) + (w.get('tss') or 0)
    # Build 52*7 = 364 day grid
    grid = []
    for i in range(365):
        day = start + timedelta(days=i)
        ds = day.strftime('%Y-%m-%d')
        grid.append({"date": ds, "tss": round(tss_map.get(ds, 0), 1), "weekday": day.weekday()})
    return {"grid": grid}

@app.post("/api/workouts/upload-gpx")
async def upload_gpx(request: Request):
    """Parses a GPX file and returns coordinates + basic stats for Leaflet mapping."""
    import gpxpy
    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    content = await file.read()
    try:
        gpx = gpxpy.parse(content)
        coords = []
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    coords.append([point.latitude, point.longitude])
        
        # very basic distance calculation
        distance_2d = gpx.length_2d()
        
        return {
            "status": "success",
            "coordinates": coords,
            "distance_m": round(distance_2d, 1)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse GPX: {str(e)}")

# ==========================================
# ENDPOINTS: AI DAILY INSIGHT
# ==========================================
@app.get("/api/coach/daily-insight")
async def get_daily_insight():
    """Proactive AI coaching insight based on current fitness state."""
    if not oai_client:
        return {"insight": "Connect your OpenAI API key for AI insights."}

    prof = db_models.get_user_profile(user_id=1)
    workouts = db_models.get_all_workouts(user_id=1)
    tss_series = [{'date': w['date'], 'tss': w['tss']} for w in workouts if w.get('tss')]
    pmc = compute_pmc_series(tss_series)

    # Build context
    latest_pmc = pmc[-1] if pmc else {}
    ramp = compute_ramp_rate(pmc) if pmc else 0
    last_workout = workouts[-1] if workouts else {}
    days_since = (datetime.today() - datetime.strptime(last_workout['date'], '%Y-%m-%d')).days if last_workout else 999

    context = (
        f"VDOT: {prof.get('current_vdot', '?')}\n"
        f"CTL (Fitness): {latest_pmc.get('ctl', 0)}, ATL (Fatigue): {latest_pmc.get('atl', 0)}, TSB (Form): {latest_pmc.get('tsb', 0)}\n"
        f"Ramp Rate: {ramp} TSS/week\n"
        f"Days since last workout: {days_since}\n"
        f"Last workout: {last_workout.get('date', 'N/A')} — {last_workout.get('sport', 'N/A')} — TSS {last_workout.get('tss', 0)}\n"
        f"Sleep: {prof.get('avg_sleep_hours', '?')}h, Stress: {prof.get('life_stress_level', '?')}\n"
    )

    system = (
        "You are APEX Coach, a world-class endurance sports coach. "
        "Analyze the athlete's current data and give ONE sharp, actionable insight in 2-3 sentences. "
        "Be direct, specific, and encouraging. Never be generic. Reference their actual numbers.\n\n"
        f"Athlete data:\n{context}\nToday: {datetime.today().strftime('%Y-%m-%d')}"
    )

    try:
        resp = oai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": "Give me today's coaching insight."}],
            temperature=0.5, max_tokens=150,
        )
        return {"insight": resp.choices[0].message.content}
    except Exception as e:
        return {"insight": f"Could not generate insight: {str(e)}"}

# ==========================================
# ENDPOINTS: TRAINING PLANS
# ==========================================
@app.post("/api/planner/generate-stream")
async def generate_plan_stream(req: PlanRequest):
    """Streams plan generation token by token. Frontend renders progressively."""
    chunks = retrieve(f"{req.goal} training plan methodology", detect_sport(req.goal))
    rag_context = "\n".join([c["content"] for c in chunks])
    
    async def event_generator():
        yield "data: {\"status\": \"generating\", \"message\": \"Building your plan...\"}\n\n"
        async for token in generate_plan_streaming(
            user_id=req.user_id, goal=req.goal, target_date=req.target_date,
            weekly_hours=req.weekly_hours, start_date=req.start_date, rag_context=rag_context
        ):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: {\"status\": \"complete\"}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/planner/score-execution")
async def score_execution(body: dict):
    planned = db_models.get_planned_workout_by_id(body["planned_workout_id"])
    if not planned: raise HTTPException(status_code=404, detail="Not found")
    execution = body["execution_data"]
    user = db_models.get_user_profile(user_id=1)
    
    splits = execution.get("splits", [])
    split_paces = [s["pace_sec_per_km"] for s in splits]
    
    if len(split_paces) > 1:
        import statistics
        mean_pace = statistics.mean(split_paces)
        std_pace = statistics.stdev(split_paces) if len(split_paces)>1 else 0
        cv = (std_pace / mean_pace) * 100 if mean_pace else 0
        pacing_pattern = "positive split (fading)" if split_paces[-1] > split_paces[0] * 1.03 else \
                         "negative split (strong finish)" if split_paces[-1] < split_paces[0] * 0.97 else \
                         "even splits"
    else:
        cv = 0
        pacing_pattern = "single effort"
    
    # Simple extraction of target pace from description
    target_pace = 300 # default
    import re
    m = re.search(r'Pace: (\d+):(\d+)', planned.get('description', ''))
    if m: target_pace = int(m.group(1))*60 + int(m.group(2))
    
    actual_avg_pace = execution.get("avg_pace_sec_per_km", target_pace)
    pace_deviation_pct = ((actual_avg_pace - target_pace) / target_pace) * 100 if target_pace else 0
    
    scoring_prompt = f"""You are a world-class endurance coach scoring a workout execution.

PLANNED WORKOUT:
- Type: {planned.get('workout_type')}
- Target: {planned.get('description')}
- Target pace: {target_pace // 60}:{target_pace % 60:02d} /km

ACTUAL EXECUTION:
- Pacing pattern: {pacing_pattern}
- Split consistency (CV): {cv:.1f}% (lower = more consistent; <3% = excellent)
- Pace vs target: {abs(pace_deviation_pct):.1f}% {'faster' if pace_deviation_pct < 0 else 'slower'} than prescribed
- Individual splits: {[f"Rep {s['rep']}: {s['pace_sec_per_km']//60}:{s['pace_sec_per_km']%60:02d}/km @ {s.get('hr','?')}bpm" for s in splits]}
- Recovery quality: {execution.get('recovery_quality', 'not recorded')}
- Athlete notes: {execution.get('notes', 'none')}

Score this workout execution on a scale of 1-10 where 10 = Perfect, 1-3 = Poor.

Respond ONLY with valid JSON:
{{
  "score": <number 1-10>,
  "grade": "<A+|A|B+|B|C+|C|D|F>",
  "headline": "<one-sentence summary>",
  "pacing_analysis": "<2 sentences about their pacing pattern>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "improvements": ["<improvement 1>", "<improvement 2>"],
  "next_session_advice": "<what to do differently next time>"
}}"""

    import openai
    oai = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    resp = await oai.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": scoring_prompt}],
        max_tokens=600,
    )
    
    result = json.loads(resp.choices[0].message.content)
    
    db_models.update_planned_workout_execution(
        planned_workout_id=body["planned_workout_id"],
        execution_data=json.dumps(execution),
        execution_score=result["score"],
        execution_feedback=json.dumps(result),
        completed=1,
    )
    
    return result

@app.get("/api/planner/current")
def get_current_plan():
    plan = db_models.get_latest_plan(user_id=1)
    if not plan:
        return {"plan": None, "workouts": []}
    workouts = db_models.get_planned_workouts(plan["id"])
    return {"plan": plan, "workouts": workouts}

# ==========================================
# ENDPOINTS: STRAVA OAUTH + WEBHOOKS
# ==========================================
@app.get("/auth/strava")
def strava_auth():
    """Redirect user to Strava OAuth consent screen."""
    if not STRAVA_CLIENT_ID:
        raise HTTPException(status_code=500, detail="STRAVA_CLIENT_ID not configured")
    redirect_uri = "http://localhost:8000/auth/strava/callback"
    url = (f"https://www.strava.com/oauth/authorize?client_id={STRAVA_CLIENT_ID}"
           f"&redirect_uri={redirect_uri}&response_type=code&scope=activity:read_all")
    return RedirectResponse(url)

@app.get("/auth/strava/callback")
async def strava_callback(code: str):
    """Exchange OAuth code for tokens, store, and sync history."""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://www.strava.com/oauth/token", data={
                "client_id": STRAVA_CLIENT_ID, "client_secret": STRAVA_CLIENT_SECRET,
                "code": code, "grant_type": "authorization_code",
            })
        data = resp.json()
        db_models.save_strava_tokens(
            strava_athlete_id=data["athlete"]["id"], access_token=data["access_token"],
            refresh_token=data["refresh_token"], expires_at=data["expires_at"],
            athlete_firstname=data["athlete"].get("firstname", ""),
        )
        # Trigger historical sync in background
        asyncio.create_task(sync_strava_history(data["access_token"]))
        return RedirectResponse("/?connected=strava")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Strava auth failed: {str(e)}")

async def get_valid_strava_token() -> str:
    """Get a valid Strava token, auto-refreshing if expired."""
    tokens = db_models.get_strava_tokens()
    if not tokens:
        raise Exception("No Strava connection")
    if tokens["strava_token_expires_at"] < time.time() + 300:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://www.strava.com/oauth/token", data={
                "client_id": STRAVA_CLIENT_ID, "client_secret": STRAVA_CLIENT_SECRET,
                "refresh_token": tokens["strava_refresh_token"], "grant_type": "refresh_token",
            })
        new = resp.json()
        db_models.update_strava_tokens(new["access_token"], new["refresh_token"], new["expires_at"])
        return new["access_token"]
    return tokens["strava_access_token"]

async def sync_strava_history(access_token: str, days_back: int = 90):
    """Pull last 90 days of Strava activities."""
    import httpx
    after_ts = int(time.time()) - (days_back * 86400)
    async with httpx.AsyncClient() as client:
        page = 1
        while True:
            resp = await client.get("https://www.strava.com/api/v3/athlete/activities",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"after": after_ts, "per_page": 50, "page": page})
            activities = resp.json()
            if not activities or not isinstance(activities, list):
                break
            for act in activities:
                await import_strava_activity(act, access_token)
            page += 1
            if len(activities) < 50:
                break

async def import_strava_activity(activity: dict, access_token: str):
    """Convert a Strava activity into an APEX workout."""
    import httpx
    async with httpx.AsyncClient() as client:
        detail_resp = await client.get(
            f"https://www.strava.com/api/v3/activities/{activity['id']}",
            headers={"Authorization": f"Bearer {access_token}"})
    detail = detail_resp.json()
    prof = db_models.get_user_profile(user_id=1)
    avg_hr = detail.get("average_heartrate")
    tss = 0
    if avg_hr and prof.get("max_hr") and prof.get("resting_hr"):
        tss = calculate_tss(activity.get("moving_time", 0), int(avg_hr), prof["max_hr"], prof["resting_hr"])
    
    classification = classify_sport(activity.get("sport_type", "Workout"))

    # Fetch heart rate and time streams from Strava
    async with httpx.AsyncClient() as client:
        streams_resp = await client.get(
            f"https://www.strava.com/api/v3/activities/{activity['id']}/streams",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"keys": "heartrate,time,distance,altitude,latlng", "key_by_type": "true"}
        )

    try:
        streams = streams_resp.json()
    except Exception:
        streams = {}

    hr_stream = json.dumps(streams.get("heartrate", {}).get("data", []))
    time_stream = json.dumps(streams.get("time", {}).get("data", []))
    laps_json = json.dumps(streams.get("latlng", {}).get("data", []))

    db_models.upsert_workout({
        "date": activity.get("start_date_local", "")[:10],
        "sport_type": activity.get("sport_type", "Workout"),
        "sport_category": classification["category"],
        "distance": round(activity.get("distance", 0) / 1000, 2) if classification["has_distance"] else None,
        "duration": activity.get("moving_time", 0),
        "elevation_gain_m": activity.get("total_elevation_gain", 0),
        "avg_hr": avg_hr, "max_hr": detail.get("max_heartrate"),
        "avg_cadence": detail.get("average_cadence"),
        "strava_activity_id": activity["id"],
        "name": activity.get("name", ""), "source": "strava",
        "tss": tss,
        "hr_stream": hr_stream,
        "time_stream": time_stream,
        "laps_json": laps_json,
    })

# Strava Webhook verification
@app.get("/webhooks/strava")
def strava_webhook_verify(hub_mode: str = None, hub_verify_token: str = None, hub_challenge: str = None):
    if hub_mode == "subscribe" and hub_verify_token == STRAVA_VERIFY_TOKEN:
        return {"hub.challenge": hub_challenge}
    raise HTTPException(status_code=403, detail="Invalid verify token")

@app.post("/webhooks/strava")
async def strava_webhook_event(request: Request):
    payload = await request.json()
    asyncio.create_task(process_strava_event(payload))
    return {"status": "received"}

async def process_strava_event(payload: dict):
    aspect = payload.get("aspect_type")
    obj_type = payload.get("object_type")
    obj_id = payload.get("object_id")
    if obj_type == "athlete" and payload.get("updates", {}).get("authorized") == "false":
        db_models.delete_strava_tokens()
        return
    if obj_type == "activity":
        try:
            token = await get_valid_strava_token()
        except Exception:
            return
        if aspect == "create":
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"https://www.strava.com/api/v3/activities/{obj_id}",
                    headers={"Authorization": f"Bearer {token}"})
            await import_strava_activity(resp.json(), token)
        elif aspect == "delete":
            db_models.delete_workout_by_strava_id(obj_id)

# ==========================================
# ENDPOINTS: CHAT
# ==========================================
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    if not oai_client:
        raise HTTPException(status_code=500, detail="OpenAI client not initialized.")
    user_message = req.messages[-1].content
    history = req.messages[:-1]
    search_query = user_message
    sport = detect_sport(user_message)
    chunks = retrieve(search_query, sport)

    async def generate():
        sources = []
        for c in chunks:
            sources.append({
                "type": c["metadata"].get("document_type", "?"),
                "sport": c["metadata"].get("sport_type", "?"),
                "score": round(c["score"], 3),
                "preview": c["content"][:150] + "..."
            })
        meta_data = {"type": "metadata", "rewritten_query": search_query, "detected_sport": sport, "sources": sources}
        yield f"data: {json.dumps(meta_data)}\n\n"
        context = "\n\n---\n\n".join(
            f"[{c['metadata'].get('document_type','?')} | sport={c['metadata'].get('sport_type','?')}]\n{c['content']}"
            for c in chunks
        )
        prof = db_models.get_user_profile(user_id=1)
        recent = db_models.get_recent_workouts(user_id=1, limit=3)
        state_str = f"ATHLETE STATE: VDOT={prof.get('current_vdot')}, Max HR={prof.get('max_hr')}, Rest HR={prof.get('resting_hr')}\n"
        if recent:
            state_str += "RECENT WORKOUTS:\n" + "\n".join([
                f"- {r['date']}: {r['distance_meters']}m in {r['duration_seconds']}s (HR: {r['avg_hr']}, RPE: {r['rpe']}, TSS: {r['tss']})"
                for r in recent])
        oai_messages = [{"role": "system", "content": SYSTEM_PROMPT + f"\n\n{state_str}\n\nRAG KNOWLEDGE_BASE:\n{context}"}]
        for msg in history[-6:]:
            oai_messages.append({"role": msg.role, "content": msg.content})
        oai_messages.append({"role": "user", "content": user_message})
        try:
            stream = oai_client.chat.completions.create(
                model=CHAT_MODEL, messages=oai_messages, temperature=0.3, max_tokens=800, stream=True)
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    yield f"data: {json.dumps({'type': 'content', 'text': delta})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

# Mount frontend
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
os.makedirs(frontend_path, exist_ok=True)
app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.routes:app", host="0.0.0.0", port=8000, reload=True)
