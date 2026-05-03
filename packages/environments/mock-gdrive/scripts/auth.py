"""OAuth2 setup for capturing golden fixtures from a real Google Drive account.

Usage:
    uv run python scripts/auth.py

This opens a browser for OAuth consent, then saves the token to scripts/token.json.
Subsequent runs of capture_fixtures.py will reuse the saved token.
"""

import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCRIPTS_DIR = Path(__file__).parent
TOKEN_PATH = SCRIPTS_DIR / "token.json"

# Find the client_secret file (name varies by GCP project)
CLIENT_SECRET_FILES = list(SCRIPTS_DIR.glob("client_secret*.json"))
if not CLIENT_SECRET_FILES:
    raise FileNotFoundError("No client_secret*.json found in scripts/. Download it from GCP Console.")
CLIENT_SECRET_PATH = CLIENT_SECRET_FILES[0]

SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_credentials() -> Credentials:
    """Get or refresh OAuth2 credentials."""
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
            # Use fixed port so EC2 users can forward it via SSH
            creds = flow.run_local_server(port=8087, open_browser=False)

        TOKEN_PATH.write_text(creds.to_json())
        print(f"Token saved to {TOKEN_PATH}")

    return creds


if __name__ == "__main__":
    creds = get_credentials()
    print(f"Authenticated successfully. Token saved to {TOKEN_PATH}")
    print(f"Scopes: {creds.scopes}")
