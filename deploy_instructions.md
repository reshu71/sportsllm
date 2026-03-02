# Deploying APEX V2 to Production

APEX Endurance Coach is designed as a monolithic Python (FastAPI) application using SQLite, making it extremely easy and cheap to deploy on free-tier cloud platforms.

## Option 1: Render.com (Recommended Free Tier)

Render provides a seamless Web Service deployment from a GitHub repository, with a built-in persistent disk for your SQLite database.

1. **Push your code to GitHub**: Create a repository and push the entire `sportsllm` directory.
2. **Create a new Web Service on Render**:
   - Connect your GitHub repository.
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt` (Ensure you create a `requirements.txt` with `fastapi`, `uvicorn`, `openai`, `chromadb`, `sentence-transformers`, `httpx`, `gpxpy`).
   - **Start Command**: `uvicorn src.api.routes:app --host 0.0.0.0 --port $PORT`
3. **Configure the SQLite Disk**:
   - In Render Advanced Settings, click "Add Disk".
   - **Mount Path**: `/opt/render/project/src/data`
   - **Size**: 1 GB is plenty.
4. **Environment Variables**:
   - `OPENAI_API_KEY` = `your_openai_key`
   - `STRAVA_CLIENT_ID` = `207285`
   - `STRAVA_CLIENT_SECRET` = `97447b21...`
   - `STRAVA_VERIFY_TOKEN` = `apex_verify`

## Option 2: Railway.app

Railway is another excellent PaaS for seamless Python deployments.

1. Install the Railway CLI or use the web dashboard to connect your GitHub repo.
2. Railway will automatically detect the Python environment.
3. Overwrite the start command in settings: `uvicorn src.api.routes:app --host 0.0.0.0 --port $PORT`
4. Add a "Volume" attached to the `/app/data` directory to ensure the ChromaDB and SQLite `apex_user.db` persist across deployments.
5. Add your `.env` variables in the Railway Variables tab.

## Post-Deployment: Strava Webhook Registration

Once your app is live and has a public URL (e.g., `https://apex-coach.onrender.com`), you **must** register the Strava webhook to receive real-time updates when an athlete logs a workout.

Run the provided script from your local machine, changing the `APEX_WEBHOOK_URL` to your new domain:

```bash
export STRAVA_CLIENT_ID=207285
export STRAVA_CLIENT_SECRET=97447b21...
export APEX_WEBHOOK_URL=https://apex-coach.onrender.com/webhooks/strava

python3 run_once/register_webhook.py
```

If successful, you will see a `200 OK` response with the subscription ID. Your app is now fully production-ready!
