"""
One-time script to obtain a YouTube OAuth refresh token.
Run this once, paste the printed refresh token into your .env file.

Usage:
    uv run python scripts/get_youtube_token.py
"""

import os
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit("YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be set in .env")

client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
credentials = flow.run_local_server(port=8080, open_browser=True)

print("\n--- Copy this into your .env ---")
print(f"YOUTUBE_REFRESH_TOKEN={credentials.refresh_token}")
print("--------------------------------\n")
