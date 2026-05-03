"""Search API routes — search.* methods."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from mock_slack.models import Channel, Message, SlackUser, Workspace
from .deps import get_db, resolve_workspace_id, resolve_token_type
from .schemas import SearchMessagesResponse, SearchMatchSchema

router = APIRouter()


@router.get("/search.messages")
def search_messages(
    query: str = Query(...),
    count: int = Query(20, ge=1, le=100),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
    token_type: Literal["bot", "user"] = Depends(resolve_token_type),
):
    if token_type == "bot":
        return JSONResponse(content={"ok": False, "error": "not_allowed_token_type"})
    # Simple text search across messages
    offset = (page - 1) * count
    messages_query = db.query(Message).filter(
        Message.workspace_id == workspace_id,
        Message.text.ilike(f"%{query}%"),
    )
    total = messages_query.count()
    messages = messages_query.order_by(Message.ts.desc()).offset(offset).limit(count).all()

    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    domain = ws.domain if ws else "workspace"
    team_id = ws.team_id if ws else ""

    matches = []
    for msg in messages:
        ch = db.query(Channel).filter(Channel.id == msg.channel_id).first()
        user = db.query(SlackUser).filter(SlackUser.id == msg.user_id).first()
        ts_url = msg.ts.replace(".", "")
        is_reply = msg.thread_ts and msg.thread_ts != msg.ts
        thread_suffix = f"?thread_ts={msg.thread_ts}" if is_reply else ""
        permalink = f"https://{domain}.slack.com/archives/{msg.channel_id}/p{ts_url}{thread_suffix}"
        match: dict = {
            "iid": msg.id,
            "type": "message",
            "text": msg.text,
            "ts": msg.ts,
            "team": team_id,
            "score": 1.0,
            "db_message": {},
            "channel": {
                "id": ch.id if ch else "",
                "name": ch.name if ch else "",
                "is_channel": True,
                "is_group": False,
                "is_im": False,
                "is_mpim": False,
                "is_shared": False,
                "is_org_shared": False,
                "is_ext_shared": False,
                "is_private": ch.is_private if ch else False,
                "is_pending_ext_shared": False,
                "pending_shared": [],
                "teams": [team_id] if team_id else [],
            },
            "user": msg.user_id,
            "username": user.name if user else "",
            "permalink": permalink,
            "blocks": [],
        }
        if is_reply:
            match["thread_ts"] = msg.thread_ts
        matches.append(match)

    pages = max(1, (total + count - 1) // count)
    first = offset + 1 if total > 0 else 0
    last = min(offset + count, total)
    return {
        "ok": True,
        "query": query,
        "messages": {
            "total": total,
            "pagination": {
                "total_count": total,
                "page": page,
                "per_page": count,
                "page_count": pages,
                "first": first,
                "last": last,
            },
            "paging": {"count": count, "total": total, "page": page, "pages": pages},
            "matches": matches,
        },
        "users": {},
        "teams": {},
        "bots": {},
    }
