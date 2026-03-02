import asyncio
from src.api.routes import sync_strava_history
from src.core.models import get_strava_tokens
import sys

async def main():
    tokens = get_strava_tokens()
    if not tokens or not tokens.get("strava_access_token"):
        print("No tokens found")
        sys.exit(1)
        
    print(f"Syncing with token: {tokens['strava_access_token'][:10]}...")
    await sync_strava_history(tokens["strava_access_token"], days_back=90)
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
