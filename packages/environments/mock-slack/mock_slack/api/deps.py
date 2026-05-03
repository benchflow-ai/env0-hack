"""Shared dependencies for API routes."""

from __future__ import annotations

import base64
from typing import Literal

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from mock_slack.models import get_session_factory


def encode_cursor(payload: str) -> str:
    """Encode a cursor payload to base64, matching real Slack cursor format."""
    return base64.b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> str | None:
    """Decode a base64 cursor, returning the payload or None if invalid."""
    try:
        return base64.b64decode(cursor.encode()).decode()
    except Exception:
        return None


def get_db() -> Session:
    """Yield a DB session."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def resolve_workspace_id(
    x_mock_slack_workspace: str | None = Header(None),
) -> str:
    """Resolve workspace ID from header or return default.

    Priority: X-Mock-Slack-Workspace header -> 'workspace_001'
    """
    if x_mock_slack_workspace:
        return x_mock_slack_workspace
    return "workspace_001"


def resolve_current_user_id(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
) -> str:
    """Return the user ID associated with the current token.

    Bot token (xoxb-) → B01MOCKBOT (the bot app user).
    User token (xoxp-) → first non-bot user in the workspace.
    """
    from mock_slack.models import SlackUser
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token.startswith("xoxp-"):
        return "B01MOCKBOT"
    user = (
        db.query(SlackUser)
        .filter(
            SlackUser.workspace_id == workspace_id,
            SlackUser.is_bot == False,
            SlackUser.id != "USLACKBOT",  # Slackbot is is_bot=False per real API; skip it
        )
        .first()
    )
    return user.id if user else ""


def resolve_token_type(
    authorization: str | None = Header(None),
) -> Literal["bot", "user"]:
    """Determine token type from Authorization header.

    xoxb-* => bot token, xoxp-* => user token.
    Defaults to 'bot' when no token is provided (conservative for testing).
    """
    if authorization:
        token = authorization.removeprefix("Bearer ").strip()
        if token.startswith("xoxp-"):
            return "user"
    return "bot"
