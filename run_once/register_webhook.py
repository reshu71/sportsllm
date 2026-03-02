"""
One-time script to register the Strava webhook subscription.
Run this AFTER deploying APEX to a public URL.

Usage:
    STRAVA_CLIENT_ID=xxx STRAVA_CLIENT_SECRET=yyy python run_once/register_webhook.py
"""
import httpx
import os

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
CALLBACK_URL = os.getenv("APEX_WEBHOOK_URL", "https://YOUR-APEX-DOMAIN.railway.app/webhooks/strava")
VERIFY_TOKEN = os.getenv("STRAVA_VERIFY_TOKEN", "apex_verify")

if not CLIENT_ID or not CLIENT_SECRET:
    print("❌ Set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET env vars first.")
    exit(1)

print(f"📡 Registering webhook at: {CALLBACK_URL}")
resp = httpx.post(
    "https://www.strava.com/api/v3/push_subscriptions",
    data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "callback_url": CALLBACK_URL,
        "verify_token": VERIFY_TOKEN,
    }
)
print(f"Response ({resp.status_code}): {resp.json()}")
