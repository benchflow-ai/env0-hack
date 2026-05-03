"""Reactions API routes — reactions.* methods."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from mock_slack.models import Channel, Message, Reaction, SlackUser, Workspace
from .deps import get_db, resolve_workspace_id
from ._helpers import _slack_error
from .schemas import (
    MessageSchema,
    ReactionItemSchema,
    EditedSchema,
    ReactionsGetResponse,
    ReactionsAddRequest,
    ReactionsRemoveRequest,
)

router = APIRouter()



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


@router.post("/reactions.add")
def reactions_add(
    body: ReactionsAddRequest,
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

    # Use first non-bot user as "current user"
    user = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace_id, SlackUser.is_bot == False
    ).first()
    if not user:
        return _slack_error("user_not_found")

    # Check for duplicate reaction
    existing = db.query(Reaction).filter(
        Reaction.message_id == msg.id,
        Reaction.user_id == user.id,
        Reaction.emoji_name == body.name,
    ).first()
    if existing:
        return _slack_error("already_reacted")

    rxn = Reaction(
        id=uuid.uuid4().hex,
        message_id=msg.id,
        user_id=user.id,
        emoji_name=body.name,
    )
    db.add(rxn)
    db.commit()
    return {"ok": True, "warning": "missing_charset", "response_metadata": {"warnings": ["missing_charset"]}}


@router.post("/reactions.remove")
def reactions_remove(
    body: ReactionsRemoveRequest,
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

    user = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace_id, SlackUser.is_bot == False
    ).first()
    if not user:
        return _slack_error("user_not_found")

    rxn = db.query(Reaction).filter(
        Reaction.message_id == msg.id,
        Reaction.user_id == user.id,
        Reaction.emoji_name == body.name,
    ).first()
    if not rxn:
        return _slack_error("no_reaction")

    db.delete(rxn)
    db.commit()
    return {"ok": True, "warning": "missing_charset", "response_metadata": {"warnings": ["missing_charset"]}}


@router.get("/reactions.get")
def reactions_get(
    channel: str = Query(...),
    timestamp: str = Query(...),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")

    msg = db.query(Message).filter(
        Message.ts == timestamp, Message.channel_id == channel
    ).first()
    if not msg:
        return _slack_error("message_not_found")

    # Get workspace team_id
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    team_id = ws.team_id if ws else ""

    return ReactionsGetResponse(
        ok=True,
        type="message",
        channel=channel,
        message=_message_to_schema(msg, team_id=team_id),
    )
