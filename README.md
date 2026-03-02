# APEX — AI-Powered Endurance Coach 🏃‍♂️🚴🏊

> A production-grade sports coaching platform rivaling Strava, Kaizen, and TrainingPeaks — built entirely on free-tier and open-source tools.

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green?logo=fastapi)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-black?logo=openai)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## What is APEX?

APEX is a **full-stack AI endurance coach** that combines three pillars into a single web application:

| Pillar | What it does |
|---|---|
| 🧠 **RAG Chat Engine** | Every answer is grounded in a curated sports science corpus via ChromaDB + cross-encoder reranking — no hallucination |
| 📐 **Deterministic Sports Science** | VDOT, TSS, PMC, HR Zones, and Race Predictions are computed using peer-reviewed formulas — never the LLM |
| 📊 **Stateful Athlete Profiling** | Your workout history, Strava streams, and training plans live in SQLite, injected into every AI interaction for personalized coaching |

---

## Features

### 💬 AI Coach (RAG-Powered Chat)
- Streaming responses grounded in 500+ sports science research chunks
- Sport-type detection with metadata-filtered retrieval
- Cross-encoder reranking for precision (BAAI/bge-reranker-base)
- Athlete-state injection (VDOT, HR zones, recent load) for personalized answers

### 📊 Athlete Dashboard
- **Time-Range Stats** — Toggle between 7 / 30 / 90-day views for activities, distance, time, and TSS
- **52-Week Training Heatmap** — GitHub-style grid colored by daily TSS
- **Activity Feed** — Clickable cards opening a Strava-style detail modal
- **Workout Detail Modal** — Heart rate line chart (Chart.js), time-in-zones bars, Leaflet GPS track overlay
- **Dynamic Coaching Insights** — AI + rule-based daily recommendations driven by TSB (Training Stress Balance)

### 📈 Analytics
- **Performance Management Chart (PMC)** — CTL / ATL / TSB line graph with form labels (Fresh / Optimal / High Risk)
- **Ramp Rate Tracking** — Weekly load change monitoring for injury prevention
- **Karvonen HR Zones** — 5-zone model with workout distribution doughnut chart
- **Race Predictor** — Riegel formula projections across 1K → Ultra distances

### 📅 AI Training Plan Generator
- **SSE Token Streaming** — Plan writes out live on screen (no loading spinner)
- **Structured JSON Output** — Periodized weekly calendar with paces, intervals, and recovery
- **Accordion Calendar View** — Color-coded by workout type (Easy / Intervals / Long / Rest)
- **ICS Export** — One-click download to Apple Calendar / Google Calendar / Outlook

### 🏆 Kaizen Workout Execution Scoring
- Log your actual splits, pacing, and RPE against the planned workout
- AI grades your execution 1–10 with structured feedback (strengths, improvements, advice)
- Chart.js sparkline comparing target vs. actual split pacing

### 🔗 Strava Integration
- **OAuth Connect** — One-click link to any Strava-connected device (Garmin, Apple Watch, Whoop, Polar)
- **90-Day History Backload** — Imports all activities with HR streams, GPS tracks, cadence, and elevation
- **Real-Time Webhooks** — New workouts auto-sync within seconds
- **Stream Data** — Second-by-second HR and GPS coordinate storage for deep analysis

### 🗺️ GPX Route Maps
- Upload standalone GPX files or view Strava-synced GPS tracks
- Leaflet.js with CARTO dark tiles for a premium map experience
- Auto-fit bounds to the route polyline

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.12 · FastAPI · Uvicorn |
| **Database** | SQLite (user data) · ChromaDB (vector store) |
| **AI/ML** | OpenAI GPT-4o-mini · text-embedding-3-small · BAAI/bge-reranker-base |
| **Frontend** | Vanilla HTML/CSS/JS · Chart.js · Leaflet.js · Lucide Icons · marked.js |
| **Integrations** | Strava OAuth 2.0 + Webhooks |
| **Deployment** | Render.com / Railway.app (free tier compatible) |

---

## Quick Start

```bash
# Clone
git clone https://github.com/reshu71/sportsllm.git
cd sportsllm

# Virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r data/requirements.txt
pip install httpx gpxpy

# Configure environment
cp .env.example .env
# Edit .env with your OPENAI_API_KEY, STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET

# Run database migration
python3 data/migrate_v3.py

# Start the server
uvicorn src.api.routes:app --reload --port 8000
```

Open **http://localhost:8000** in your browser.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | OpenAI API key for GPT-4o-mini + embeddings |
| `STRAVA_CLIENT_ID` | ✅ | From your [Strava API app](https://www.strava.com/settings/api) |
| `STRAVA_CLIENT_SECRET` | ✅ | From your Strava API app |
| `STRAVA_VERIFY_TOKEN` | Optional | Webhook verification (default: `apex_verify`) |

---

## Project Structure

```
sportsllm/
├── run.py                          # Uvicorn entrypoint
├── src/
│   ├── api/routes.py               # 20+ FastAPI endpoints
│   ├── core/models.py              # Pydantic schemas + SQLite ORM
│   ├── services/
│   │   ├── sports_science.py       # VDOT, TSS, PMC, HR zones, Riegel
│   │   └── planner.py              # LLM plan generator (SSE streaming)
│   └── frontend/
│       ├── index.html              # SPA shell (4-tab layout)
│       ├── style.css               # Dark theme design system
│       └── app.js                  # Client-side controller (1,100 lines)
├── data/
│   ├── apex_user.db                # SQLite database (auto-created)
│   ├── endurance_db/               # ChromaDB vector store
│   ├── migrate_v3.py               # Schema migration script
│   └── requirements.txt            # Python dependencies
└── run_once/
    └── register_webhook.py         # Strava webhook registration
```

> 📖 For detailed technical documentation, see [DOCUMENTATION.md](DOCUMENTATION.md).

---

## Sports Science Algorithms

| Algorithm | Formula | Source |
|---|---|---|
| **VDOT** | Daniels/Gilbert O₂ cost model | Jack Daniels' Running Formula |
| **Race Prediction** | `T₂ = T₁ × (D₂/D₁)^1.06` | Pete Riegel (1981) |
| **TSS** | `(duration × IF² × 100) / 3600` | Andrew Coggan |
| **CTL/ATL/TSB** | Exponential moving averages (42d / 7d) | TrainingPeaks PMC model |
| **HR Zones** | Karvonen Heart Rate Reserve | Karvonen (1957) |

---

## Deployment

### Render.com (Recommended)
1. Push to GitHub → Connect repo on Render
2. **Build**: `pip install -r data/requirements.txt`
3. **Start**: `uvicorn src.api.routes:app --host 0.0.0.0 --port $PORT`
4. Add persistent disk at `/opt/render/project/src/data` (1 GB)
5. Set environment variables in dashboard

### Railway.app
1. Connect GitHub repo → set start command
2. Add Volume at `/app/data`
3. Set env vars in the Variables tab

After deployment, register the Strava webhook:
```bash
python3 run_once/register_webhook.py
```

---

## License

MIT

---

<p align="center">
  Built with ❤️ by <a href="https://github.com/reshu71">reshu71</a> · Powered by RAG + Sports Science
</p>
