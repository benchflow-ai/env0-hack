"""
One-time setup: save your Slack bot token to scripts/slack_token.json.

Usage:
    python scripts/slack_auth.py

This will:
1. Read SLACK_BOT_TOKEN from slack_token.json (or env var as fallback)
2. Call auth.test to verify the token
3. Print workspace name, bot user, and team ID — no personal info stored

Token file format (scripts/slack_token.json — gitignored):
    {
        "bot_token": "xoxb-...",
        "user_token": "xoxp-..."   (optional, for user-scoped endpoints)
    }

To get tokens:
  - Go to api.slack.com/apps → your app → OAuth & Permissions
  - Bot token: "Bot User OAuth Token" (xoxb-...)
  - User token: "User OAuth Token" (xoxp-...) — only needed for user-scoped endpoints
"""

import json
import os
import sys
from pathlib import Path

import requests

SCRIPTS_DIR = Path(__file__).parent
TOKEN_FILE = SCRIPTS_DIR / "slack_token.json"


def load_token() -> dict:
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())

    # Fallback: read from environment variables
    bot = os.environ.get("SLACK_BOT_TOKEN")
    user = os.environ.get("SLACK_USER_TOKEN")
    if bot:
        print(f"slack_token.json not found — using SLACK_BOT_TOKEN from environment")
        tokens = {"bot_token": bot}
        if user:
            tokens["user_token"] = user
        return tokens

    print("ERROR: No token found.")
    print(f"  Create {TOKEN_FILE} with your bot token, or set SLACK_BOT_TOKEN env var.")
    print(f"  See scripts/slack_token.json.example for the format.")
    sys.exit(1)


def verify_token(token: str, label: str) -> dict:
    resp = requests.post(
        "https://slack.com/api/auth.test",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        print(f"ERROR: {label} invalid — {data.get('error')}")
        sys.exit(1)
    return data


def main():
    tokens = load_token()

    bot_token = tokens.get("bot_token")
    if not bot_token:
        print("ERROR: slack_token.json must contain 'bot_token'")
        sys.exit(1)

    print("=== Bot token ===")
    bot_info = verify_token(bot_token, "bot_token")
    print(f"  Workspace : {bot_info['team']}  (team_id={bot_info['team_id']})")
    print(f"  Bot user  : {bot_info['user']}  (user_id={bot_info['user_id']})")
    print(f"  URL       : {bot_info.get('url', 'n/a')}")

    user_token = tokens.get("user_token")
    if user_token:
        print("\n=== User token ===")
        user_info = verify_token(user_token, "user_token")
        print(f"  Workspace : {user_info['team']}  (team_id={user_info['team_id']})")
        print(f"  User      : {user_info['user']}  (user_id={user_info['user_id']})")
    else:
        print("\n(No user_token in slack_token.json — skipping user token check)")

    print("\nTokens verified. Ready to run capture_fixtures.py.")


if __name__ == "__main__":
    main()
