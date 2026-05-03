"""Team API routes — team.* methods."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from mock_slack.models import Workspace
from .deps import get_db, resolve_workspace_id
from .schemas import WorkspaceSchema, TeamInfoResponse

router = APIRouter()


def _slack_error(error: str) -> JSONResponse:
    return JSONResponse(content={"ok": False, "error": error})


@router.get("/team.info")
def team_info(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        return _slack_error("team_not_found")
    return TeamInfoResponse(
        ok=True,
        team=WorkspaceSchema(
            id=ws.id,
            name=ws.name,
            domain=ws.domain or "",
            url=f"https://{ws.domain}.slack.com/",
            email_domain="",
            avatar_base_url="https://ca.slack-edge.com/",
            is_verified=False,
            discoverable="closed",
            enterprise_id=ws.team_id or "",
            enterprise_name=ws.name,
            enterprise_domain=ws.domain or "",
            lob_sales_home_enabled=False,
            is_sfdc_auto_slack=False,
            icon={"image_default": True},
        ),
    )
