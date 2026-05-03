"""Chat/Messages API routes — chat.* methods."""

from __future__ import annotations

import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from mock_slack.models import Channel, ChannelMember, Message, SlackUser, Workspace, ScheduledMessage, InviteTrigger
from .deps import get_db, resolve_workspace_id
from ._helpers import _slack_error
from .schemas import (
    MessageSchema,
    EditedSchema,
    ReactionItemSchema,
    PostMessageResponse,
    ChatUpdateResponse,
    PermalinkResponse,
    ChatPostMessageRequest,
    ChatPostEphemeralRequest,
    ChatUpdateRequest,
    ChatDeleteRequest,
    ChatScheduleMessageRequest,
    ChatDeleteScheduledMessageRequest,
)

router = APIRouter()


def _make_ts() -> str:
    """Generate a Slack-style timestamp string."""
    t = time.time()
    return f"{t:.6f}"


def _message_to_schema(
    msg: Message,
    team_id: str = "",
    include_bot_fields: bool = False,
    include_language: bool = True,
) -> MessageSchema:
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
    language = {"locale": "en", "is_reliable": True} if include_language else None

    bot_id = None
    app_id = None
    bot_profile = None
    if include_bot_fields:
        bot_id = "B000000MOCK"
        app_id = "A000000MOCK"
        bot_profile = {
            "id": "B000000MOCK",
            "app_id": "A000000MOCK",
            "name": "Mock Bot",
            "icons": {},
            "deleted": False,
            "updated": 0,
            "team_id": team_id,
        }

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
        attachments=msg.attachments or None,
        language=language,
        bot_id=bot_id,
        app_id=app_id,
        bot_profile=bot_profile,
    )



@router.post("/chat.postMessage")
def chat_post_message(
    body: ChatPostMessageRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")
    if ch.is_archived:
        return _slack_error("is_archived")

    # Resolve posting user — first non-bot user in workspace
    user = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace_id, SlackUser.is_bot == False
    ).first()
    if not user:
        return _slack_error("user_not_found")

    # Get workspace team_id
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    team_id = ws.team_id if ws else ""

    ts = _make_ts()
    msg_id = uuid.uuid4().hex

    # Determine thread_ts
    thread_ts = body.thread_ts
    if thread_ts:
        # Validate parent message exists
        parent = db.query(Message).filter(
            Message.ts == thread_ts, Message.channel_id == body.channel
        ).first()
        if not parent:
            return _slack_error("thread_not_found")
        # Update parent reply_count
        parent.reply_count = (parent.reply_count or 0) + 1
    else:
        thread_ts = ts  # parent message points to itself

    msg = Message(
        id=msg_id,
        channel_id=body.channel,
        workspace_id=workspace_id,
        user_id=user.id,
        text=body.text,
        ts=ts,
        thread_ts=thread_ts,
        attachments=body.attachments or None,
        created_at=datetime.utcnow(),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Fire invite triggers: if this is a DM to a user who is a trigger target,
    # auto-invite B01MOCKBOT to the associated private channel.
    if ch.is_im:
        # Find the DM recipient (the non-sender member of this IM channel)
        dm_members = db.query(ChannelMember).filter(ChannelMember.channel_id == ch.id).all()
        for dm_member in dm_members:
            triggers = db.query(InviteTrigger).filter(
                InviteTrigger.workspace_id == workspace_id,
                InviteTrigger.trigger_user_id == dm_member.user_id,
            ).all()
            for trigger in triggers:
                already = db.query(ChannelMember).filter(
                    ChannelMember.channel_id == trigger.channel_id,
                    ChannelMember.user_id == "B01MOCKBOT",
                ).first()
                if not already:
                    db.add(ChannelMember(
                        channel_id=trigger.channel_id,
                        user_id="B01MOCKBOT",
                    ))
        db.commit()

    return PostMessageResponse(
        ok=True,
        channel=body.channel,
        ts=ts,
        message=_message_to_schema(msg, team_id=team_id, include_bot_fields=True, include_language=False),
    )


@router.post("/chat.postEphemeral")
def chat_post_ephemeral(
    body: ChatPostEphemeralRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")
    # Ephemeral messages aren't persisted in mock
    ts = _make_ts()
    return {"ok": True, "message_ts": ts, "warning": "missing_charset", "response_metadata": {"warnings": ["missing_charset"]}}


@router.post("/chat.update")
def chat_update(
    body: ChatUpdateRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")

    msg = db.query(Message).filter(
        Message.ts == body.ts, Message.channel_id == body.channel
    ).first()
    if not msg:
        return _slack_error("message_not_found")

    # Get workspace team_id
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    team_id = ws.team_id if ws else ""

    msg.text = body.text
    msg.is_edited = True
    edited_ts = _make_ts()
    msg.edited_ts = edited_ts
    db.commit()
    db.refresh(msg)

    message_dict = {
        "text": msg.text,
        "user": msg.user_id,
        "team": team_id,
        "edited": {"user": msg.user_id, "ts": edited_ts},
    }

    return ChatUpdateResponse(
        ok=True,
        channel=body.channel,
        ts=body.ts,
        text=msg.text,
        message=message_dict,
    )


@router.post("/chat.delete")
def chat_delete(
    body: ChatDeleteRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")

    msg = db.query(Message).filter(
        Message.ts == body.ts, Message.channel_id == body.channel
    ).first()
    if not msg:
        return _slack_error("message_not_found")

    # If this is a thread parent, also decrement parent reply count for replies
    if msg.thread_ts and msg.thread_ts != msg.ts:
        parent = db.query(Message).filter(
            Message.ts == msg.thread_ts, Message.channel_id == body.channel
        ).first()
        if parent and parent.reply_count and parent.reply_count > 0:
            parent.reply_count -= 1

    # Remove associated reactions and pins
    from mock_slack.models import Reaction, Pin
    db.query(Reaction).filter(Reaction.message_id == msg.id).delete()
    db.query(Pin).filter(Pin.message_id == msg.id).delete()
    db.delete(msg)
    db.commit()

    return {"ok": True, "channel": body.channel, "ts": body.ts, "warning": "missing_charset", "response_metadata": {"warnings": ["missing_charset"]}}


@router.get("/chat.getPermalink")
def chat_get_permalink(
    channel: str = Query(...),
    message_ts: str = Query(...),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")

    msg = db.query(Message).filter(
        Message.ts == message_ts, Message.channel_id == channel
    ).first()
    if not msg:
        return _slack_error("message_not_found")

    # Get workspace domain for permalink
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    domain = ws.domain if ws else "workspace"
    # Convert ts to URL-friendly format (remove the dot)
    ts_url = message_ts.replace(".", "")
    permalink = f"https://{domain}.slack.com/archives/{channel}/p{ts_url}"

    return PermalinkResponse(ok=True, channel=channel, permalink=permalink)


@router.post("/chat.scheduleMessage")
def chat_schedule_message(
    body: ChatScheduleMessageRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")
    if ch.is_archived:
        return _slack_error("is_archived")

    user = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace_id, SlackUser.is_bot == False
    ).first()
    if not user:
        return _slack_error("user_not_found")

    now = int(time.time())
    if body.post_at <= now:
        return _slack_error("time_in_past")

    scheduled_id = "Sm" + uuid.uuid4().hex[:10].upper()
    sched = ScheduledMessage(
        id=scheduled_id,
        channel_id=body.channel,
        workspace_id=workspace_id,
        user_id=user.id,
        text=body.text,
        post_at=body.post_at,
        thread_ts=body.thread_ts,
        date_created=now,
        is_delivered=False,
    )
    db.add(sched)
    db.commit()

    return {
        "ok": True,
        "channel": body.channel,
        "scheduled_message_id": scheduled_id,
        "post_at": body.post_at,
        "message": {
            "text": body.text,
            "username": user.real_name or user.id,
            "bot_id": None,
            "type": "delayed_message",
            "subtype": "scheduled_message",
        },
    }


@router.post("/chat.deleteScheduledMessage")
def chat_delete_scheduled_message(
    body: ChatDeleteScheduledMessageRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")

    sched = db.query(ScheduledMessage).filter(
        ScheduledMessage.id == body.scheduled_message_id,
        ScheduledMessage.channel_id == body.channel,
        ScheduledMessage.workspace_id == workspace_id,
    ).first()
    if not sched:
        return _slack_error("invalid_scheduled_message_id")
    if sched.is_delivered:
        return _slack_error("already_sent")

    db.delete(sched)
    db.commit()
    return {"ok": True}


@router.get("/chat.scheduledMessages.list")
def chat_scheduled_messages_list(
    channel: str | None = Query(None),
    oldest: int | None = Query(None),
    latest: int | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    now = int(time.time())

    # Auto-deliver any scheduled messages whose post_at has passed
    due = db.query(ScheduledMessage).filter(
        ScheduledMessage.workspace_id == workspace_id,
        ScheduledMessage.is_delivered == False,
        ScheduledMessage.post_at <= now,
    ).all()
    for sched in due:
        ch = db.query(Channel).filter(Channel.id == sched.channel_id).first()
        if ch and not ch.is_archived:
            ts = f"{sched.post_at}.000000"
            msg_id = uuid.uuid4().hex
            thread_ts = sched.thread_ts if sched.thread_ts else ts
            msg = Message(
                id=msg_id,
                channel_id=sched.channel_id,
                workspace_id=workspace_id,
                user_id=sched.user_id,
                text=sched.text,
                ts=ts,
                thread_ts=thread_ts,
                created_at=datetime.utcfromtimestamp(sched.post_at),
            )
            db.add(msg)
        sched.is_delivered = True
    if due:
        db.commit()

    # Query pending (not yet delivered) scheduled messages
    query = db.query(ScheduledMessage).filter(
        ScheduledMessage.workspace_id == workspace_id,
        ScheduledMessage.is_delivered == False,
    )
    if channel:
        query = query.filter(ScheduledMessage.channel_id == channel)
    if oldest is not None:
        query = query.filter(ScheduledMessage.post_at >= oldest)
    if latest is not None:
        query = query.filter(ScheduledMessage.post_at <= latest)

    scheduled = query.order_by(ScheduledMessage.post_at.asc()).limit(limit).all()
    return {
        "ok": True,
        "scheduled_messages": [
            {
                "id": s.id,
                "channel_id": s.channel_id,
                "post_at": s.post_at,
                "date_created": s.date_created,
                "text": s.text,
            }
            for s in scheduled
        ],
        "response_metadata": {"next_cursor": ""},
    }
