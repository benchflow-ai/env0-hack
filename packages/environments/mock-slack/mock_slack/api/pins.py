"""Pins API routes — pins.* methods."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from mock_slack.models import Channel, Message, Pin, SlackUser, Workspace
from .deps import get_db, resolve_workspace_id
from .schemas import (
    MessageSchema,
    ReactionItemSchema,
    EditedSchema,
    PinItemSchema,
    PinsListResponse,
    PinsAddRequest,
    PinsRemoveRequest,
)

router = APIRouter()


def _slack_error(error: str) -> JSONResponse:
    return JSONResponse(content={"ok": False, "error": error})


def _message_to_schema(msg: Message, team_id: str = "") -> MessageSchema:
    rxn_map: dict[str, list[str]] = {}
    for rxn in msg.reactions:
        rxn_map.setdefault(rxn.emoji_name, []).append(rxn.user_id)
    reactions = [
        ReactionItemSchema(name=name, count=len(users), users=users)
        for name, users in rxn_map.items()
    ] or None
    edited = None
    if msg.is_edited and msg.edited_ts:
        edited = EditedSchema(user=msg.user_id, ts=msg.edited_ts)

    blocks = [{"type": "rich_text", "block_id": "mock", "elements": [{"type": "rich_text_section", "elements": [{"type": "text", "text": msg.text}]}]}]
    language = {"locale": "en", "is_reliable": True}

    return MessageSchema(
        type="message",
        user=msg.user_id,
        text=msg.text,
        ts=msg.ts,
        team=team_id or None,
        thread_ts=msg.thread_ts if msg.thread_ts and msg.thread_ts != msg.ts else None,
        reply_count=msg.reply_count if msg.reply_count else None,
        reactions=reactions,
        edited=edited,
        blocks=blocks,
        language=language,
    )


@router.post("/pins.add")
def pins_add(
    body: PinsAddRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")

    msg = db.query(Message).filter(
        Message.ts == body.timestamp, Message.channel_id == body.channel
    ).first()
    if not msg:
        return _slack_error("message_not_found")

    # Check for duplicate pin
    existing_pin = db.query(Pin).filter(
        Pin.channel_id == body.channel, Pin.message_id == msg.id
    ).first()
    if existing_pin:
        return _slack_error("already_pinned")

    user = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace_id, SlackUser.is_bot == False
    ).first()
    if not user:
        return _slack_error("user_not_found")

    pin = Pin(
        id=uuid.uuid4().hex,
        channel_id=body.channel,
        message_id=msg.id,
        user_id=user.id,
        created_at=datetime.utcnow(),
    )
    db.add(pin)
    msg.is_pinned = True
    db.commit()
    return {"ok": True, "warning": "missing_charset", "response_metadata": {"warnings": ["missing_charset"]}}


@router.post("/pins.remove")
def pins_remove(
    body: PinsRemoveRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")

    msg = db.query(Message).filter(
        Message.ts == body.timestamp, Message.channel_id == body.channel
    ).first()
    if not msg:
        return _slack_error("message_not_found")

    pin = db.query(Pin).filter(
        Pin.channel_id == body.channel, Pin.message_id == msg.id
    ).first()
    if not pin:
        return _slack_error("no_pin")

    db.delete(pin)
    msg.is_pinned = False
    db.commit()
    return {"ok": True, "warning": "missing_charset", "response_metadata": {"warnings": ["missing_charset"]}}


@router.get("/pins.list")
def pins_list(
    channel: str = Query(...),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")

    # Get workspace team_id
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    team_id = ws.team_id if ws else ""

    pins = db.query(Pin).filter(Pin.channel_id == channel).all()
    items = []
    for p in pins:
        msg = db.query(Message).filter(Message.id == p.message_id).first()
        if msg:
            items.append(PinItemSchema(
                type="message",
                channel=channel,
                message=_message_to_schema(msg, team_id=team_id),
                created=int(p.created_at.timestamp()) if p.created_at else 0,
                created_by=p.user_id,
            ))

    return PinsListResponse(ok=True, items=items)
