# APEX Endurance AI Coach — Complete Technical Documentation

> **Version**: 3.0 (V3 Master Upgrade)
> **Last Updated**: 2026-03-02
> **Stack**: Python 3.12 · FastAPI · SQLite · ChromaDB · OpenAI GPT-4o-mini · Leaflet.js · Chart.js

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Repository Structure](#3-repository-structure)
4. [Backend Modules](#4-backend-modules)
   - 4.1 [API Routes (`routes.py`)](#41-api-routes)
   - 4.2 [Database Models (`models.py`)](#42-database-models)
   - 4.3 [Sports Science Engine (`sports_science.py`)](#43-sports-science-engine)
   - 4.4 [AI Training Planner (`planner.py`)](#44-ai-training-planner)
5. [Database Schema](#5-database-schema)
6. [Frontend](#6-frontend)
   - 6.1 [HTML Structure (`index.html`)](#61-html-structure)
   - 6.2 [Design System (`style.css`)](#62-design-system)
   - 6.3 [Client Application (`app.js`)](#63-client-application)
7. [API Reference](#7-api-reference)
8. [Strava Integration](#8-strava-integration)
9. [RAG Pipeline](#9-rag-pipeline)
10. [Dependencies & Environment](#10-dependencies--environment)
11. [Deployment](#11-deployment)
12. [V3 Upgrade Changelog](#12-v3-upgrade-changelog)

---

## 1. Overview

APEX is a **production-grade, AI-powered endurance sports coaching platform** that fuses three technologies into a single web application:

| Pillar | What it does |
|---|---|
| **Retrieval-Augmented Generation (RAG)** | Grounds every AI answer in a curated corpus of sports science research, preventing hallucination |
| **Deterministic Sports Science** | Computes VDOT, TSS, PMC, HR Zones, and Race Predictions using peer-reviewed formulas — never the LLM |
| **Stateful Athlete Profiling** | Stores the athlete's profile, workout history, Strava streams, and training plans in SQLite, injecting this context into every LLM interaction |

The platform is designed to rival **Strava**, **Kaizen**, **Intervals.icu**, and **TrainingPeaks** — built entirely on free-tier and open-source tools.

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        BROWSER CLIENT                        │
│  index.html · style.css · app.js                             │
│  Chart.js · Leaflet.js · Lucide · marked.js                 │
└────────────────────────────┬─────────────────────────────────┘
                             │ HTTP / SSE
┌────────────────────────────▼─────────────────────────────────┐
│                    FastAPI (routes.py)                        │
│                                                              │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐       │
│  │ RAG      │  │ Sports       │  │ AI Planner       │       │
│  │ Pipeline │  │ Science      │  │ Service           │       │
│  │          │  │ Engine       │  │                   │       │
│  │ ChromaDB │  │ VDOT/TSS/PMC│  │ gpt-4o-mini       │       │
│  │ Reranker │  │ HR Zones    │  │ JSON streaming    │       │
│  │ OpenAI   │  │ Riegel      │  │                   │       │
│  └──────────┘  └──────────────┘  └──────────────────┘       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │ SQLite Database (apex_user.db)                    │       │
│  │ users · workouts · training_plans · planned_workouts │    │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Strava OAuth + Webhooks                           │       │
│  │ Token management · Activity import · Stream fetch │       │
│  └──────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Chat**: User query → embed with OpenAI → ChromaDB top-8 → cross-encoder rerank top-3 → inject athlete state → GPT-4o-mini SSE stream
2. **Workout Log**: User submits form → compute TSS/VDOT → store in SQLite → optionally update profile VDOT
3. **Strava Sync**: OAuth callback → backload 90 days → webhook for real-time → fetch HR/time/latlng streams → store in SQLite
4. **Plan Generation**: User sets goal → fetch RAG context → GPT-4o-mini JSON streaming → parse + persist day-by-day workouts
5. **Execution Scoring**: User logs splits → GPT-4o-mini grades 1-10 → persist score + feedback

---

## 3. Repository Structure

```
sportsllm/
├── run.py                              # Uvicorn entrypoint (host 0.0.0.0:8000)
├── .env                                # Environment variables
├── DOCUMENTATION.md                    # ← This file
├── deploy_instructions.md              # Render / Railway deploy guide
├── manual_sync.py                      # Manual Strava re-sync utility
├── sample.gpx                          # Test GPX file
├── test_api.py                         # Basic API tests
│
├── data/
│   ├── apex_user.db                    # SQLite database (auto-created)
│   ├── endurance_db/                   # ChromaDB persistent vector store
│   ├── migrate_v2.py                   # V2 schema migration script
│   ├── migrate_v3.py                   # V3 schema migration script
│   ├── requirements.txt                # Python dependencies
│   ├── app.py                          # Legacy data processing (deprecated)
│   ├── data_fetch.py                   # Corpus ingestion pipeline
│   └── kaggle_data/                    # External training datasets
│
├── src/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py                   # All 20+ FastAPI endpoints (704 lines)
│   ├── core/
│   │   ├── __init__.py
│   │   └── models.py                   # Pydantic schemas + SQLite ORM (326 lines)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── sports_science.py           # Deterministic formulas (225 lines)
│   │   └── planner.py                  # LLM plan generator (122 lines)
│   └── frontend/
│       ├── index.html                  # HTML shell (436 lines)
│       ├── style.css                   # Design system (1,126 lines)
│       └── app.js                      # Client-side logic (1,100 lines)
│
└── run_once/
    └── register_webhook.py             # One-time Strava webhook registration
```

---

## 4. Backend Modules

### 4.1 API Routes

**File**: `src/api/routes.py` (704 lines)

The monolithic FastAPI application file. It initializes ChromaDB, the OpenAI client, the cross-encoder reranker, and serves the static frontend.

#### Key Globals

| Variable | Value | Purpose |
|---|---|---|
| `EMBED_MODEL` | `text-embedding-3-small` | OpenAI embedding model for vector queries |
| `RERANKER_MODEL` | `BAAI/bge-reranker-base` | Cross-encoder for precision reranking |
| `CHAT_MODEL` | `gpt-4o-mini` | LLM for chat, insights, and scoring |
| `COARSE_K` | `8` | Number of initial ChromaDB results |
| `FINAL_K` | `3` | Number of chunks after reranking |

#### Internal Functions

| Function | Purpose |
|---|---|
| `cached(key, ttl)` | Simple TTL-based in-memory response cache decorator |
| `detect_sport(query)` | Keyword-based sport detection for metadata filtering |
| `retrieve(query, sport)` | Full RAG pipeline: embed → ChromaDB → rerank → return top chunks |
| `get_valid_strava_token()` | Auto-refreshes expired Strava OAuth tokens |
| `sync_strava_history(token, days)` | Backloads N days of Strava activities |
| `import_strava_activity(activity, token)` | Converts a single Strava activity into a local workout with streams |
| `process_strava_event(payload)` | Handles incoming Strava webhook events |

---

### 4.2 Database Models

**File**: `src/core/models.py` (326 lines)

Contains Pydantic schemas for API transfer and all SQLite interaction functions.

#### Pydantic Schemas

| Schema | Fields | Usage |
|---|---|---|
| `UserProfile` | name, age, weight_kg, max_hr, resting_hr, current_vdot, unit_preference, avg_sleep_hours, life_stress_level | Athlete profile for LLM context |
| `TrainingPlan` | id, goal, target_date, weekly_hours, created_at | Plan metadata |
| `PlannedWorkout` | id, plan_id, date, sport, workout_type, planned_distance_meters, planned_duration_seconds, description, completed | Individual scheduled workout |
| `WorkoutLog` | date, sport, distance_meters, duration_seconds, avg_hr, rpe | Manual workout entry |
| `GoalLog` | race_date, target_distance_meters, target_time_seconds | Race targets |

#### Database Functions (27 total)

| Function | Purpose |
|---|---|
| `init_db()` | Creates all tables if they don't exist |
| `get_user_profile(user_id)` | Returns athlete profile as dict |
| `update_user_vdot(new_vdot, user_id)` | Updates VDOT after breakthrough workouts |
| `log_workout(w, tss, vdot_estimate, user_id)` | Inserts a manually logged workout |
| `get_recent_workouts(user_id, limit)` | Returns N most recent workouts |
| `create_training_plan(user_id, goal, target_date, weekly_hours)` | Creates plan and returns plan_id |
| `add_planned_workout(plan_id, ...)` | Inserts one planned workout row |
| `get_latest_plan(user_id)` | Returns most recent plan |
| `get_planned_workouts(plan_id)` | Returns all workouts for a plan |
| `get_planned_workout_by_id(workout_id)` | Returns a single planned workout |
| `update_planned_workout_execution(id, data, score, feedback, completed)` | Persists Kaizen execution results |
| `get_all_workouts(user_id)` | Full workout history ordered by date |
| `save_strava_tokens(...)` | Persists OAuth tokens after Strava connect |
| `get_strava_tokens(user_id)` | Retrieves stored Strava tokens |
| `update_strava_tokens(...)` | Saves refreshed tokens |
| `delete_strava_tokens(user_id)` | Removes tokens on de-authorization |
| `upsert_workout(data, user_id)` | Insert-or-skip by strava_activity_id (includes streams) |
| `delete_workout_by_strava_id(strava_id)` | Removes a Strava-synced workout |

---

### 4.3 Sports Science Engine

**File**: `src/services/sports_science.py` (225 lines)

All deterministic calculations that bypass the LLM for precision.

#### Sport Classification System

- **`DISTANCE_SPORTS`**: Set of Strava sport types that report meaningful distance (Run, Ride, Swim, etc.)
- **`NON_DISTANCE_SPORTS`**: Yoga, WeightTraining, CrossFit, etc. — distance is set to `None`
- **`SPORT_CATEGORIES`**: Maps every Strava `sport_type` to a normalized category (running, cycling, swimming, strength, flexibility, etc.)
- **`SPORT_ICONS`**: Emoji mapping per category for UI display

| Function | Formula | Purpose |
|---|---|---|
| `classify_sport(sport_type)` | Lookup tables | Returns `{category, has_distance, icon, label}` — fixes the "0km Yoga" bug |
| `calculate_vdot(distance_m, time_s)` | Daniels/Gilbert O₂ cost model | Approximates effective VO₂max from race performance |
| `predict_race_time(dist1, time1, dist2)` | `T₂ = T₁ × (D₂/D₁)^1.06` | Pete Riegel's formula for multi-distance prediction |
| `predict_all_race_times(km, sec)` | Riegel across 1K-Ultra | Returns dict of predicted times for 7 standard distances |
| `calculate_tss(duration, avg_hr, max_hr, rest_hr)` | `TSS = (dur × IF² × 100) / 3600` | Heart Rate Reserve-based Training Stress Score |
| `compute_pmc_series(workouts)` | Exponential moving averages | Day-by-day CTL (42-day), ATL (7-day), TSB values |
| `compute_ramp_rate(pmc_series)` | CTL delta over 7 days | Weekly load change — safe: 5-8, danger: >10 |
| `calculate_hr_zones(max_hr, rest_hr)` | Karvonen (Heart Rate Reserve) | 5-zone model with min/max HR per zone |
| `classify_workout_zone(avg_hr, max_hr, rest_hr)` | Zone boundaries | Returns zone name for a given average HR |
| `format_time(seconds)` | Division | Formats seconds into `HH:MM:SS` or `MM:SS` |

---

### 4.4 AI Training Planner

**File**: `src/services/planner.py` (122 lines)

Uses OpenAI's **JSON mode** (`response_format: { type: "json_object" }`) to force structured output.

#### JSON Output Schema

```json
{
  "plan_name": "string",
  "goal": "string",
  "total_weeks": "number",
  "weeks": [
    {
      "week_number": 1,
      "focus": "Base Building",
      "total_tss": "number",
      "workouts": [
        {
          "day": "Monday",
          "type": "Easy Run",
          "distance_km": "number",
          "duration_min": "number",
          "pace_min_per_km": "number",
          "description": "string",
          "key_intervals": []
        }
      ]
    }
  ]
}
```

#### `generate_plan_streaming()`

1. Loads athlete profile (VDOT, HR, stress level)
2. Constructs a system prompt combining the JSON schema, athlete state, and RAG methodology context
3. Streams tokens from `gpt-4o-mini` via `AsyncOpenAI`
4. Yields each token delta for SSE progressive rendering
5. On completion, parses the full JSON buffer and persists each workout to `planned_workouts` table
6. Maps day names (Monday-Sunday) to real dates starting from `start_date`

---

## 5. Database Schema

### `users` Table

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment user ID |
| name | TEXT | Athlete name (from Strava or manual) |
| age | INTEGER | Current age |
| weight_kg | REAL | Body weight |
| max_hr | INTEGER | Maximum heart rate |
| resting_hr | INTEGER | Resting heart rate |
| current_vdot | REAL | Effective VO₂max estimate |
| unit_preference | TEXT | `km` or `mi` |
| avg_sleep_hours | REAL | Average sleep per night |
| life_stress_level | TEXT | `low`, `moderate`, `high` |
| strava_athlete_id | INTEGER | Strava athlete numeric ID |
| strava_access_token | TEXT | OAuth access token |
| strava_refresh_token | TEXT | OAuth refresh token |
| strava_token_expires_at | INTEGER | Unix timestamp of token expiry |
| strava_connected | INTEGER | 0 or 1 flag |
| ftp_watts | REAL | Functional Threshold Power (cycling) |
| lthr | REAL | Lactate Threshold Heart Rate |
| preferred_sport | TEXT | Default sport type |

### `workouts` Table

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment workout ID |
| user_id | INTEGER FK | References `users.id` |
| date | TEXT | `YYYY-MM-DD` |
| sport | TEXT | Legacy sport field |
| sport_type | TEXT | Raw Strava sport_type (e.g., `TrailRun`, `Yoga`) |
| sport_category | TEXT | Normalized category (e.g., `running`, `flexibility`) |
| distance_meters | REAL | Total distance in meters |
| duration_seconds | INTEGER | Moving time in seconds |
| avg_hr | INTEGER | Average heart rate |
| max_hr | INTEGER | Maximum heart rate in session |
| avg_cadence | INTEGER | Average cadence (steps/min or rpm) |
| rpe | INTEGER | Rating of Perceived Exertion (1-10) |
| tss | REAL | Computed Training Stress Score |
| vdot_estimate | REAL | Estimated VDOT from this workout |
| strava_activity_id | INTEGER | Strava's unique activity ID (for dedup) |
| source | TEXT | `manual` or `strava` |
| name | TEXT | Activity name (from Strava) |
| elevation_gain_m | REAL | Total elevation gain in meters |
| hr_stream | TEXT | JSON array of second-by-second HR values |
| time_stream | TEXT | JSON array of elapsed time values |
| laps_json | TEXT | JSON array of `[lat, lng]` coordinate pairs (GPS track) |
| notes | TEXT | Free-text notes |
| perceived_effort | INTEGER | Strava's perceived effort field |
| workout_execution_score | REAL | AI-generated execution score (1-10) |
| execution_notes | TEXT | AI-generated feedback |

### `training_plans` Table

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment plan ID |
| user_id | INTEGER FK | References `users.id` |
| goal | TEXT | Target race goal (e.g., "Sub-20 5k") |
| target_date | TEXT | Race date |
| weekly_hours | REAL | Available training hours per week |
| created_at | TEXT | Plan creation timestamp |

### `planned_workouts` Table

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| plan_id | INTEGER FK | References `training_plans.id` |
| date | TEXT | Scheduled date |
| sport | TEXT | Sport type |
| workout_type | TEXT | E.g., `Easy Run`, `Intervals`, `Long Run` |
| planned_distance_meters | REAL | Target distance |
| planned_duration_seconds | REAL | Target duration |
| description | TEXT | Detailed workout description with paces |
| completed | INTEGER | 0 = pending, 1 = done |
| execution_data | TEXT | JSON of user-entered splits/notes |
| execution_score | REAL | AI-graded score (1-10) |
| execution_feedback | TEXT | AI-generated coaching feedback |

### `goals` Table

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| user_id | INTEGER FK | References `users.id` |
| race_date | TEXT | Target race date |
| target_distance_meters | REAL | Race distance |
| target_time_seconds | REAL | Target finish time |

---

## 6. Frontend

### 6.1 HTML Structure

**File**: `src/frontend/index.html` (436 lines)

Single-page application with a 4-tab sidebar navigation:

| Tab | View ID | Content |
|---|---|---|
| **AI Coach** | `chat-wrapper` | RAG-powered streaming chat with suggested prompts |
| **Dashboard** | `dashboard-wrapper` | Stats bar, heatmap, GPX map, activity feed, workout log form |
| **Analytics** | `analytics-wrapper` | PMC chart, HR zones table, zone distribution chart, race predictor |
| **Training Plan** | `plan-wrapper` | Plan calendar, execution scoring modal, ICS export |

#### External Libraries Loaded

| Library | CDN | Version | Purpose |
|---|---|---|---|
| Lucide | unpkg.com | Latest | Icon system (SVG) |
| Chart.js | jsdelivr.net | 4.x | Line, bar, doughnut charts |
| marked.js | jsdelivr.net | Latest | Markdown-to-HTML rendering for chat |
| Leaflet.js | unpkg.com | 1.9.4 | Interactive GPS map tiles |

#### Modal Components

1. **Plan Generation Modal** (`#plan-modal`): Form with goal, race date, weekly hours → triggers SSE plan generation
2. **Workout Detail Modal** (`#workout-detail-modal`): Strava-style overlay with distance/time/HR stats, Leaflet GPS map, Chart.js HR line graph, and time-in-zones bar visualization
3. **Execution Modal** (dynamically injected): Split entry form for Kaizen workout scoring

---

### 6.2 Design System

**File**: `src/frontend/style.css` (1,126 lines)

Dark-themed "space" aesthetic with glassmorphism cards.

#### CSS Custom Properties

| Variable | Value | Usage |
|---|---|---|
| `--apex-black` | `#0a0a0f` | Body background |
| `--apex-dark` | `#111118` | Sidebar background |
| `--apex-card` | `#16161f` | Card backgrounds |
| `--apex-primary` | `#00d4ff` | Accent / brand color (cyan) |
| `--apex-secondary` | `#ff6b35` | Secondary accent (orange) |
| `--apex-success` | `#00e676` | Positive state (green) |
| `--apex-warning` | `#ffd600` | Warning state (yellow) |
| `--apex-danger` | `#ff1744` | Error state (red) |
| `--font-heading` | `Space Grotesk` | Headings and navigation |
| `--font-mono` | `JetBrains Mono` | Numeric values and code |

#### Key CSS Classes

| Class | Purpose |
|---|---|
| `.app-container` | Flex row layout (sidebar + main) |
| `.sidebar` | Fixed 210px left navigation with brand, tabs, integrations |
| `.main-content` | Scrollable content area |
| `.apex-card` | Glassmorphism card with subtle border and glow |
| `.stats-row` | Grid row of stat cards |
| `.stat-card` | Individual metric card with icon + value + label |
| `.heatmap-grid` | CSS grid for 52-week TSS heatmap |
| `.chat-container` | Chat message feed container |
| `.msg-user` / `.msg-assistant` | Chat bubble styles |
| `.plan-calendar` | Accordion week-by-week calendar |
| `.skeleton-*` | Loading placeholder animations (pulse) |

---

### 6.3 Client Application

**File**: `src/frontend/app.js` (1,100 lines)

Vanilla JavaScript SPA controller — no frameworks, no build step.

#### Core Functions (39 total)

**Tab Navigation**:
- `switchTab(tab)` — Manages view switching, triggers data loading per tab

**Dashboard (Section 5)**:
- `loadDashboard()` — Parallel fetch of profile, heatmap, PMC; triggers stats loading
- `fetchDashboardStats(days)` — Fetches `/api/workouts?period=N`, computes aggregates, updates stat cards
- `renderHeatmap(grid)` — Renders 52-week TSS heatmap with color coding
- `renderRecentWorkouts(workouts)` — Renders clickable activity feed cards
- `loadDailyInsight()` — Fetches AI coaching insight and appends to insight card

**Workout Detail Modal (Section 5 + 6)**:
- `showWorkoutDetail(workoutId)` — Opens slide-over modal with stats, Leaflet GPS map, Chart.js HR line, zone bars
- `closeWorkoutDetail()` — Hides the modal overlay

**Map Viewer (Section 6)**:
- `initMap()` — Initializes Leaflet map instance with CARTO dark tiles
- `handleGPXUpload(event)` — Uploads GPX file, draws polyline on dashboard map

**Analytics**:
- `loadAnalytics()` — Fetches PMC and zone data
- `renderPMCChart(series)` — Chart.js line graph (CTL/ATL/TSB)
- `renderZoneTable(zones)` — HTML table of Karvonen HR zones
- `renderZoneChart(distribution)` — Chart.js doughnut chart of zone distribution
- `predictRaces()` — Calls backend race predictor, renders formatted results table

**Training Plan (Section 4 + 7)**:
- `loadPlan()` — Fetches current plan, formats for calendar, renders
- `formatPlanForCalendar(dbPlan, dbWorkouts)` — Groups workouts by week
- `renderPlanCalendar(plan)` — Renders accordion calendar with color-coded workout types
- `toggleWeek(num)` — Expands/collapses a calendar week
- `ensureExecutionModal()` — Lazy-creates the execution logging DOM
- `openExecution(workoutId, event)` — Opens Kaizen scoring form (intervals or simple)
- `closeExecution()` — Closes the execution modal
- `parsePaceToSec(paceStr)` — Converts "M:SS" pace string to seconds
- `scoreExecution(workoutId, isInterval, numReps)` — Collects form data, POSTs to backend, renders result
- `renderScoreCard(scoreData, splits)` — Displays AI score, feedback, and Chart.js sparkline
- `showPlanSkeleton()` — Displays skeleton loading UI during plan generation
- `exportICS()` — Generates and downloads .ics calendar file from plan workouts

**Chat**:
- `addMessage(role, content)` — Appends a chat bubble to the feed
- `sendMessage()` — SSE streaming chat with source citation rendering
- `renderSources(sources)` — Displays RAG citation cards in sidebar
- `setPrompt(text)` — Sets textarea content from suggested prompt chips

---

## 7. API Reference

### User & Workouts

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/profile` | None | Returns user profile + 5 recent workouts |
| `POST` | `/api/workouts` | None | Logs a workout, computes TSS/VDOT, updates profile |
| `GET` | `/api/workouts?period=N` | None | Returns all workouts from the last N days |

### Analytics

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/analytics/pmc` | None | PMC series (CTL, ATL, TSB), ramp rate, form label |
| `GET` | `/api/analytics/zones` | None | HR zone boundaries + workout zone distribution |
| `GET` | `/api/analytics/heatmap` | None | 52-week workout-per-day grid with TSS color coding |
| `GET` | `/api/stats/streaks` | None | Current streak, longest streak, total workouts, weekly TSS |
| `POST` | `/api/analytics/predict` | None | Race time predictions from a known result using Riegel formula |

### AI Coach

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/chat` | None | RAG-powered streaming chat (SSE). Sends `messages[]` array |
| `GET` | `/api/coach/daily-insight` | None | Proactive AI coaching insight based on fitness state (cached 1hr) |

### Training Plans

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/planner/generate-stream` | None | SSE streaming plan generation from goal/date/hours |
| `GET` | `/api/planner/current` | None | Returns latest plan metadata + all planned workouts |
| `POST` | `/api/planner/score-execution` | None | Kaizen execution scoring — sends splits, gets AI grade 1-10 |

### File Upload

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/workouts/upload-gpx` | None | Parses GPX file, returns coordinates array for Leaflet |

### Strava Integration

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/auth/strava` | None | Redirects to Strava OAuth consent screen |
| `GET` | `/auth/strava/callback` | None | Exchanges code for tokens, syncs 90-day history |
| `GET` | `/webhooks/strava` | None | Webhook verification endpoint (hub challenge) |
| `POST` | `/webhooks/strava` | None | Receives create/update/delete activity events |

---

## 8. Strava Integration

### OAuth Flow

1. User clicks **"Connect Strava"** → redirected to `https://www.strava.com/oauth/authorize` with scopes `read,activity:read_all`
2. User authorizes → Strava redirects to `/auth/strava/callback?code=XXX`
3. Backend exchanges code for `access_token` + `refresh_token` → stores in `users` table
4. Backend immediately calls `sync_strava_history()` to backload 90 days

### Activity Import Pipeline

For each Strava activity:

1. Fetch detailed activity from `GET /api/v3/activities/{id}`
2. Fetch streams from `GET /api/v3/activities/{id}/streams` with keys: `heartrate, time, distance, altitude, latlng`
3. Classify sport type using `classify_sport()` — determines category, whether to show distance, and icon
4. Compute TSS using Heart Rate Reserve method
5. Store everything via `upsert_workout()` including `hr_stream`, `time_stream`, and `laps_json` (GPS coordinates)
6. Deduplication: Skip if `strava_activity_id` already exists

### Webhook Events

| Event Type | Object | Action |
|---|---|---|
| `create` | `activity` | Fetch activity details and import |
| `update` | `activity` | Re-import (currently same as create) |
| `delete` | `activity` | Delete from local database |
| `update` | `athlete` (authorized=false) | De-authorize — delete stored tokens |

### Token Auto-Refresh

`get_valid_strava_token()` checks if `strava_token_expires_at < now + 300s`. If expired, it calls `POST https://www.strava.com/oauth/token` with the refresh token to get a new access token.

---

## 9. RAG Pipeline

### Corpus

| Source | File | Content |
|---|---|---|
| Hand-curated sports science | Ingested into ChromaDB | ~200+ chunks on VO₂max, lactate threshold, periodization, nutrition, pacing |
| Endurance metrics | Ingested into ChromaDB | ~150+ chunks on HR zones, power, TSS, CTL/ATL training theory |
| Wikipedia articles | Scraped & chunked | 10 articles (VO2 max, Marathon, HIIT, Periodization, etc.) |

### Pipeline Steps

```
User Query
    │
    ▼
┌─────────────────────┐
│ 1. Sport Detection   │  Keyword matching → optional metadata filter
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 2. Embed Query       │  OpenAI text-embedding-3-small → 1536-dim vector
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 3. ChromaDB Search   │  Top-8 nearest neighbors (with sport filter)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 4. Cross-Encoder     │  BAAI/bge-reranker-base scores all 8
│    Reranking         │  Selects top-3 by relevance score
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 5. Context Assembly  │  RAG chunks + athlete profile + system prompt
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 6. GPT-4o-mini       │  SSE streaming response
│    Generation        │  Grounded in both science and athlete state
└─────────────────────┘
```

### System Prompt

The system prompt instructs APEX to behave as an elite AI endurance coach with expertise in:
- Triathlon, marathon, cycling, swimming
- Exercise physiology and sports nutrition
- Training methodology (Daniels, Pfitzinger, 80/20)

It also injects real-time athlete state (VDOT, HR zones, recent TSS, form status) so responses are personalized.

---

## 10. Dependencies & Environment

### Python Dependencies (`requirements.txt`)

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | ≥0.110.0 | Web framework |
| `uvicorn[standard]` | ≥0.29.0 | ASGI server |
| `sse-starlette` | ≥1.8.2 | Server-Sent Events support |
| `openai` | ≥1.30.0 | GPT-4o-mini + embeddings |
| `chromadb` | ≥0.5.0 | Vector database for RAG |
| `sentence-transformers` | ≥3.0.0 | Cross-encoder reranker model |
| `tiktoken` | ≥0.7.0 | Token counting (context window management) |
| `rich` | ≥13.7.0 | Console formatting |
| `python-dotenv` | ≥1.0.0 | `.env` file loading |

Additional runtime dependencies (not in requirements.txt but used):
- `httpx` — Async HTTP client for Strava API calls
- `gpxpy` — GPX file parsing

### Environment Variables (`.env`)

| Variable | Required | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | OpenAI API authentication |
| `STRAVA_CLIENT_ID` | ✅ | Strava app client ID |
| `STRAVA_CLIENT_SECRET` | ✅ | Strava app client secret |
| `STRAVA_VERIFY_TOKEN` | Optional | Webhook verification token (default: `apex_verify`) |
| `APEX_WEBHOOK_URL` | Optional | Production webhook URL for registration |

---

## 11. Deployment

### Local Development

```bash
cd sportsllm

# Create virtual environment
python3 -m venv sportsllm
source sportsllm/bin/activate

# Install dependencies
pip install -r data/requirements.txt
pip install httpx gpxpy

# Run database migration (first time or after upgrade)
python3 data/migrate_v3.py

# Start server
uvicorn src.api.routes:app --reload --port 8000
```

The app is then accessible at `http://localhost:8000`.

### Production (Render.com — Recommended)

1. Push code to GitHub
2. Create Web Service on Render.com
3. **Build Command**: `pip install -r data/requirements.txt`
4. **Start Command**: `uvicorn src.api.routes:app --host 0.0.0.0 --port $PORT`
5. Add a **persistent disk** mounted at `/opt/render/project/src/data` (1 GB)
6. Set environment variables in the Render dashboard
7. After deployment, register the Strava webhook:

```bash
python3 run_once/register_webhook.py
```

### Production (Railway.app)

1. Connect GitHub repo
2. Override start command: `uvicorn src.api.routes:app --host 0.0.0.0 --port $PORT`
3. Add a Volume at `/app/data`
4. Set environment variables in the Variables tab

---

## 12. V3 Upgrade Changelog

### Section 0 — Codebase Cleanup
- Removed redundant data processing scripts
- Cleared `__pycache__` and `.pyc` files
- Wired up previously dead UI elements

### Section 1 — Database Migration (V3 Schema)
- Created `data/migrate_v3.py` — adds 22 new columns across `workouts`, `planned_workouts`, and `users`
- Supports HR/time/GPS streams, Strava tokens, execution scoring, and sport categorization

### Section 2 — Sport Type Mapping Fix
- Added `classify_sport()` function with 40+ Strava sport type mappings
- Fixed the "0km Yoga" bug — non-distance sports now show duration instead
- Updated `import_strava_activity()` to use the new classification pipeline

### Section 3 — Plan Generation Speed (SSE)
- Replaced synchronous plan generation with async token streaming
- Added SSE endpoint `/api/planner/generate-stream`
- Implemented skeleton UI loaders with CSS pulse animations

### Section 4 — Kaizen Workout Execution Scoring
- Built execution form modal with split entry (intervals + simple mode)
- Created `/api/planner/score-execution` endpoint — GPT-4o-mini analyzes planned vs. actual effort
- Generates a 1-10 score with structured feedback (analysis, strengths, improvements, advice)
- Added Chart.js sparkline for split pacing visualization

### Section 5 — Dashboard Redesign
- Added `GET /api/workouts?period=N` endpoint with rolling date window
- Implemented time-range filter buttons (7 / 30 / 90 Days)
- Rebuilt the Recent Activity feed as clickable card list
- Added Strava-style Workout Detail slide-over modal with:
  - HR line chart (Chart.js, second-by-second data)
  - Time-in-Zones bar visualization (5-zone Karvonen)
  - Leaflet GPS track overlay
- Wired dynamic coaching Focus Areas using TSB thresholds

### Section 6 — GPX Route Maps
- Extended Strava stream fetch to include `latlng` coordinates
- Updated `upsert_workout()` to persist GPS data as `laps_json`
- Added Leaflet polyline rendering inside the Workout Detail modal
- Handles `invalidateSize()` timing for correct map rendering after modal open

### Section 7 — Training Plan Visual Calendar
- Converted flat workout list into accordion-style weekly calendar
- Color-coded workout types (Easy = green, Intervals = red, Long = blue, etc.)
- Integrated execution scoring buttons directly into each workout row

### Section 8 — Final Integration
- Fixed `Query` import missing from FastAPI
- Fixed `sqlite3` import missing from routes
- Verified full application flow via browser testing
