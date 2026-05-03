"""Auth API routes — auth.* methods."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from mock_slack.models import Workspace, SlackUser
from .deps import get_db, resolve_workspace_id
from .schemas import AuthTestResponse

router = APIRouter()


def _slack_error(error: str) -> JSONResponse:
    return JSONResponse(content={"ok": False, "error": error})


@router.post("/auth.test")
def auth_test(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        return _slack_error("team_not_found")

    # Find first non-bot user as the "authed" user
    user = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace_id, SlackUser.is_bot == False
    ).first()
    if not user:
        return _slack_error("user_not_found")

    # Find bot user
    bot = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace_id, SlackUser.is_bot == True
    ).first()

    return AuthTestResponse(
        ok=True,
        url=f"https://{ws.domain}.slack.com/",
        team=ws.name,
        user=user.name,
        team_id=ws.team_id or ws.id,
        user_id=user.id,
        bot_id=bot.id if bot else None,
        enterprise_id="",
        is_enterprise_install=False,
    )
