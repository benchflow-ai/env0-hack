#!/usr/bin/env python3
"""One-time OAuth flow for Google Docs + Drive API.

Usage:
    1. Create a GCP project and enable Google Docs API + Google Drive API.
    2. Create OAuth 2.0 credentials (Desktop app) and download as credentials.json
       into this directory (scripts/credentials.json).
    3. Run: python scripts/auth.py
    4. A browser window opens for consent. Token is saved to scripts/token.json.

Subsequent runs reuse the saved token (refreshing if needed).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
CREDENTIALS_PATH = SCRIPTS_DIR / "credentials.json"
TOKEN_PATH = SCRIPTS_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


def authenticate():
    """Run OAuth flow and return credentials."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            "Missing dependencies. Install with:\n"
            "  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client",
            file=sys.stderr,
        )
        sys.exit(1)

    creds = None

    # Load existing token
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # Refresh or run new flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token...")
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                print(
                    f"credentials.json not found at {CREDENTIALS_PATH}\n"
                    "Download OAuth credentials from GCP Console → APIs & Services → Credentials",
                    file=sys.stderr,
                )
                sys.exit(1)

            print("Starting OAuth consent flow (browser will open)...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token
        TOKEN_PATH.write_text(creds.to_json())
        print(f"Token saved to {TOKEN_PATH}")

    # Verify by listing a few docs
    from googleapiclient.discovery import build

    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)

    # Quick check: list first 3 docs
    results = drive_service.files().list(
        q="mimeType='application/vnd.google-apps.document'",
        pageSize=3,
        fields="files(id, name)",
    ).execute()

    files = results.get("files", [])
    print(f"\nAuthentication successful!")
    print(f"Found {len(files)} document(s):")
    for f in files:
        print(f"  - {f['name']} ({f['id']})")

    return creds


if __name__ == "__main__":
    authenticate()
