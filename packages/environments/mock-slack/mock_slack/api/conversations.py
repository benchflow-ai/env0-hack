"""Conversations API routes — conversations.* methods."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from mock_slack.models import Channel, ChannelMember, Message, SlackUser, Workspace
from .deps import get_db, resolve_workspace_id, resolve_current_user_id, resolve_token_type, encode_cursor, decode_cursor
from ._helpers import _slack_error
from pydantic import BaseModel

from .schemas import (
    ChannelSchema,
    IMChannelSchema,
    ChannelTopicSchema,
    ChannelPurposeSchema,
    ConversationsListResponse,
    ConversationInfoResponse,
    ConversationMembersResponse,
    MessagesListResponse,
    MessageSchema,
    ReactionItemSchema,
    EditedSchema,
    ConversationsCreateRequest,
    ConversationsRenameRequest,
    ConversationsInviteRequest,
    ConversationsKickRequest,
    ConversationsPurposeRequest,
    ConversationsTopicRequest,
    ConversationsOpenRequest,
)


class _ChannelBody(BaseModel):
    channel: str

router = APIRouter()


def _is_member(channel: Channel, db: Session, user_id: str) -> bool:
    """Return True if user_id is a member of the channel."""
    return db.query(ChannelMember).filter(
        ChannelMember.channel_id == channel.id,
        ChannelMember.user_id == user_id,
    ).first() is not None


def _channel_base_dict(channel: Channel, db: Session, current_user_id: str = "", token_type: str = "bot") -> dict:
    """Build the base channel dict (fields common to all channel responses)."""
    created_ts = int(channel.created_at.timestamp()) if channel.created_at else 0

    # Get workspace team_id
    ws = db.query(Workspace).filter(Workspace.id == channel.workspace_id).first()
    team_id = ws.team_id if ws else ""

    d = {
        "id": channel.id,
        "name": channel.name,
        "is_channel": not channel.is_im and not channel.is_mpim,
        "is_group": channel.is_private and not channel.is_im and not channel.is_mpim,
        "is_im": channel.is_im,
        "is_mpim": channel.is_mpim,
        "is_private": channel.is_private,
        "is_archived": channel.is_archived,
        "is_general": channel.name == "general",
        "is_shared": False,
        "is_org_shared": False,
        "is_ext_shared": False,
        "is_pending_ext_shared": False,
        "is_member": _is_member(channel, db, current_user_id) if current_user_id else True,
        "is_moved": 0,
        "creator": channel.creator_id or "",
        "name_normalized": channel.name,
        "topic": {"value": channel.topic or "", "creator": "", "last_set": 0},
        "purpose": {"value": channel.purpose or "", "creator": "", "last_set": 0},
        "created": created_ts,
        "updated": created_ts,
        "unlinked": 0,
        "context_team_id": team_id,
        "parent_conversation": None,
        "pending_shared": [],
        "pending_connected_team_ids": [],
        "shared_team_ids": [],
        "internal_team_ids": [],
        "previous_names": [],
    }

    # last_read is only returned for user tokens, not bot tokens
    if token_type == "user":
        latest_msg = (
            db.query(Message)
            .filter(Message.channel_id == channel.id)
            .order_by(Message.ts.desc())
            .first()
        )
        d["last_read"] = latest_msg.ts if latest_msg else "0"

    return d


def _channel_to_schema(channel: Channel, db: Session, current_user_id: str = "", token_type: str = "bot") -> dict:
    """Return channel dict for conversations.info (no num_members — real API omits it here)."""
    d = _channel_base_dict(channel, db, current_user_id, token_type=token_type)
    d["properties"] = {
        "tabs": [
            {"type": "bookmarks", "label": "", "id": "bookmarks"},
            {"type": "files", "label": "", "id": "files"},
        ],
        "tabz": [{"type": "bookmarks"}, {"type": "files"}],
    }
    return d


def _channel_to_schema_list(channel: Channel, db: Session, current_user_id: str = "", token_type: str = "bot") -> dict:
    """Return channel dict for conversations.list (includes num_members)."""
    d = _channel_base_dict(channel, db, current_user_id, token_type=token_type)
    d["num_members"] = db.query(ChannelMember).filter(ChannelMember.channel_id == channel.id).count()
    d["properties"] = {
        "tabs": [
            {"type": "bookmarks", "label": "", "id": "bookmarks"},
            {"type": "files", "label": "", "id": "files"},
        ],
        "tabz": [{"type": "bookmarks"}, {"type": "files"}],
    }
    return d


def _channel_to_schema_create(channel: Channel, db: Session, token_type: str = "bot") -> dict:
    """Return channel dict for create/mutation endpoints (has 'priority', no 'properties', no 'num_members')."""
    d = _channel_base_dict(channel, db, token_type=token_type)
    d["priority"] = 0
    return d


def _im_channel_to_schema(channel: Channel, db: Session) -> IMChannelSchema:
    created_ts = int(channel.created_at.timestamp()) if channel.created_at else 0
    # Get workspace team_id
    ws = db.query(Workspace).filter(Workspace.id == channel.workspace_id).first()
    team_id = ws.team_id if ws else ""
    # Get the other user in the DM (not the creator)
    members = db.query(ChannelMember).filter(ChannelMember.channel_id == channel.id).all()
    other_user = ""
    for m in members:
        if m.user_id != channel.creator_id:
            other_user = m.user_id
            break
    if not other_user and members:
        other_user = members[0].user_id
    return IMChannelSchema(
        id=channel.id,
        created=created_ts,
        is_im=True,
        is_org_shared=False,
        is_archived=channel.is_archived,
        is_shared=False,
        context_team_id=team_id,
        updated=created_ts,
        user=other_user,
        is_user_deleted=False,
        priority=0,
    )


def _message_to_schema(
    msg: Message,
    team_id: str = "",
    parent_user_id: str | None = None,
    is_locked: bool | None = None,
    subscribed: bool | None = None,
    latest_reply: str | None = None,
    reply_users_count: int | None = None,
    reply_users: list[str] | None = None,
    db: Session | None = None,
) -> MessageSchema:
    from mock_slack.models import Reaction as ReactionModel
    # Aggregate reactions
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

    # Check if message author is a bot — include bot fields if so
    bot_id = None
    bot_profile = None
    subtype = None
    if db is not None:
        author = db.query(SlackUser).filter(SlackUser.id == msg.user_id).first()
        if author and author.is_bot:
            bot_id = msg.user_id
            subtype = "bot_message"
            bot_profile = {
                "id": msg.user_id,
                "app_id": "A000000MOCK",
                "name": author.real_name or author.name,
                "icons": {},
                "deleted": False,
                "updated": 0,
                "team_id": team_id,
            }

    return MessageSchema(
        type="message",
        subtype=subtype,
        user=msg.user_id,
        text=msg.text,
        ts=msg.ts,
        team=team_id or None,
        thread_ts=msg.thread_ts if msg.thread_ts and msg.thread_ts != msg.ts else None,
        reply_count=msg.reply_count if msg.reply_count else None,
        reactions=reactions,
        edited=edited,
        blocks=blocks,
        parent_user_id=parent_user_id,
        is_locked=is_locked,
        subscribed=subscribed,
        latest_reply=latest_reply,
        reply_users_count=reply_users_count,
        reply_users=reply_users,
        bot_id=bot_id,
        bot_profile=bot_profile,
    )



@router.get("/conversations.list")
def conversations_list(
    exclude_archived: bool = Query(False),
    types: str = Query("public_channel"),
    limit: int = Query(200, ge=1, le=1000),
    cursor: str | None = Query(None),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
    current_user_id: str = Depends(resolve_current_user_id),
    token_type: str = Depends(resolve_token_type),
):
    query = db.query(Channel).filter(Channel.workspace_id == workspace_id)
    if exclude_archived:
        query = query.filter(Channel.is_archived == False)

    # Filter by type — build an OR filter from the requested types
    type_list = [t.strip() for t in types.split(",")]
    want_public = "public_channel" in type_list
    want_private = "private_channel" in type_list
    want_im = "im" in type_list

    # Default: public channels only (matches real Slack API default)
    if not want_public and not want_private and not want_im:
        want_public = True

    from sqlalchemy import or_
    type_filters = []
    if want_public:
        type_filters.append(
            (Channel.is_private == False) & (Channel.is_im == False) & (Channel.is_mpim == False)
        )
    if want_private:
        # Private channels: only return channels where the caller is a member
        member_channel_ids = [
            m.channel_id for m in
            db.query(ChannelMember).filter(ChannelMember.user_id == current_user_id).all()
        ]
        if member_channel_ids:
            type_filters.append(
                (Channel.is_private == True) & (Channel.is_im == False) & Channel.id.in_(member_channel_ids)
            )
    if want_im:
        type_filters.append(Channel.is_im == True)

    if type_filters:
        query = query.filter(or_(*type_filters))
    else:
        # Fallback: public channels only
        query = query.filter(Channel.is_private == False, Channel.is_im == False, Channel.is_mpim == False)

    # Cursor-based pagination: cursor encodes "after:<channel_id>"
    if cursor:
        payload = decode_cursor(cursor)
        if payload and payload.startswith("after:"):
            after_id = payload[len("after:"):]
            query = query.filter(Channel.id > after_id)

    query = query.order_by(Channel.id.asc())
    channels = query.limit(limit + 1).all()

    has_more = len(channels) > limit
    channels = channels[:limit]

    # Use IM schema for IM channels, list schema (with num_members) for others
    channel_schemas = []
    for c in channels:
        if c.is_im:
            channel_schemas.append(_im_channel_to_schema(c, db).model_dump())
        else:
            channel_schemas.append(_channel_to_schema_list(c, db, current_user_id, token_type=token_type))

    next_cursor = encode_cursor(f"after:{channels[-1].id}") if has_more and channels else ""
    return ConversationsListResponse(
        ok=True,
        channels=channel_schemas,
        response_metadata={"next_cursor": next_cursor},
    )


@router.get("/conversations.info")
def conversations_info(
    channel: str = Query(...),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
    current_user_id: str = Depends(resolve_current_user_id),
    token_type: str = Depends(resolve_token_type),
):
    ch = db.query(Channel).filter(
        Channel.id == channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")
    if ch.is_private and not ch.is_im and not _is_member(ch, db, current_user_id):
        return _slack_error("channel_not_found")
    return ConversationInfoResponse(ok=True, channel=_channel_to_schema(ch, db, current_user_id, token_type=token_type))


@router.post("/conversations.create")
def conversations_create(
    body: ConversationsCreateRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
    token_type: str = Depends(resolve_token_type),
):
    # Check for duplicate name
    existing = db.query(Channel).filter(
        Channel.workspace_id == workspace_id,
        Channel.name == body.name,
    ).first()
    if existing:
        return _slack_error("name_taken")

    channel_id = "C" + uuid.uuid4().hex[:8].upper()
    # Find any user to be creator; fallback to "system"
    first_user = db.query(SlackUser).filter(SlackUser.workspace_id == workspace_id).first()
    creator_id = first_user.id if first_user else "USLACKBOT"

    ch = Channel(
        id=channel_id,
        workspace_id=workspace_id,
        name=body.name.lower().replace(" ", "-"),
        is_private=body.is_private,
        creator_id=creator_id,
        created_at=datetime.utcnow(),
    )
    db.add(ch)
    # Add creator as member
    db.add(ChannelMember(channel_id=channel_id, user_id=creator_id))
    db.commit()
    db.refresh(ch)
    return {
        "ok": True,
        "channel": _channel_to_schema_create(ch, db, token_type=token_type),
        "warning": "missing_charset",
        "response_metadata": {"warnings": ["missing_charset"]},
    }


@router.post("/conversations.open")
def conversations_open(
    body: ConversationsOpenRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
    current_user_id: str = Depends(resolve_current_user_id),
):
    # Case 1: channel ID provided — open an existing DM/channel directly
    if body.channel:
        ch = db.query(Channel).filter(
            Channel.id == body.channel, Channel.workspace_id == workspace_id
        ).first()
        if not ch:
            return _slack_error("channel_not_found")
        return {
            "ok": True,
            "no_op": True,
            "already_open": True,
            "channel": _im_channel_to_schema(ch, db).model_dump(),
        }

    # Case 2: users provided — find or create DM
    if not body.users:
        return _slack_error("invalid_arguments")

    # Always include the caller so we find/create a channel with both members.
    # If current_user_id is a bot placeholder (no auth token), fall back to
    # the first non-bot human user in the workspace.
    caller_id = current_user_id
    caller = db.query(SlackUser).filter(
        SlackUser.id == caller_id,
        SlackUser.workspace_id == workspace_id,
        SlackUser.is_bot == False,
    ).first()
    if not caller:
        caller = db.query(SlackUser).filter(
            SlackUser.workspace_id == workspace_id,
            SlackUser.is_bot == False,
        ).first()
        if caller:
            caller_id = caller.id

    raw_ids = set(u.strip() for u in body.users.split(",") if u.strip())
    if caller_id:
        raw_ids.add(caller_id)
    user_ids = sorted(raw_ids)
    if not user_ids:
        return _slack_error("invalid_arguments")

    # Validate all users exist
    for uid in user_ids:
        if not db.query(SlackUser).filter(SlackUser.id == uid, SlackUser.workspace_id == workspace_id).first():
            return _slack_error("user_not_found")

    # Look for an existing IM channel with exactly these members
    is_mpim = len(user_ids) > 2
    existing_dm = None
    candidate_channels = db.query(Channel).filter(
        Channel.workspace_id == workspace_id,
        Channel.is_im == (not is_mpim),
        Channel.is_mpim == is_mpim,
    ).all()
    for ch in candidate_channels:
        members = db.query(ChannelMember).filter(ChannelMember.channel_id == ch.id).all()
        member_ids = sorted(m.user_id for m in members)
        if member_ids == user_ids:
            existing_dm = ch
            break

    if existing_dm:
        return {
            "ok": True,
            "no_op": True,
            "already_open": True,
            "channel": _im_channel_to_schema(existing_dm, db).model_dump(),
        }

    # Create new DM channel
    prefix = "G" if is_mpim else "D"
    channel_id = prefix + uuid.uuid4().hex[:8].upper()
    ch = Channel(
        id=channel_id,
        workspace_id=workspace_id,
        name=f"dm-{'-'.join(user_ids)}",
        is_private=True,
        is_im=not is_mpim,
        is_mpim=is_mpim,
        creator_id=user_ids[0],
        created_at=datetime.utcnow(),
    )
    db.add(ch)
    for uid in user_ids:
        db.add(ChannelMember(channel_id=channel_id, user_id=uid))
    db.commit()
    db.refresh(ch)
    return {
        "ok": True,
        "no_op": False,
        "already_open": False,
        "channel": _im_channel_to_schema(ch, db).model_dump(),
    }


@router.post("/conversations.archive")
def conversations_archive(
    body: _ChannelBody,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")
    if ch.is_archived:
        return _slack_error("already_archived")
    ch.is_archived = True
    db.commit()
    return {"ok": True, "warning": "missing_charset", "response_metadata": {"warnings": ["missing_charset"]}}


@router.post("/conversations.unarchive")
def conversations_unarchive(
    body: _ChannelBody,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")
    if not ch.is_archived:
        return _slack_error("not_archived")
    ch.is_archived = False
    db.commit()
    return {"ok": True, "warning": "missing_charset", "response_metadata": {"warnings": ["missing_charset"]}}


@router.post("/conversations.rename")
def conversations_rename(
    body: ConversationsRenameRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")
    new_name = body.name.lower().replace(" ", "-")
    # Check duplicate
    existing = db.query(Channel).filter(
        Channel.workspace_id == workspace_id,
        Channel.name == new_name,
        Channel.id != body.channel,
    ).first()
    if existing:
        return _slack_error("name_taken")
    ch.name = new_name
    db.commit()
    db.refresh(ch)
    return {
        "ok": True,
        "channel": _channel_to_schema(ch, db),
        "warning": "missing_charset",
        "response_metadata": {"warnings": ["missing_charset"]},
    }


@router.post("/conversations.invite")
def conversations_invite(
    body: ConversationsInviteRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")

    user_ids = [u.strip() for u in body.users.split(",") if u.strip()]
    for user_id in user_ids:
        user = db.query(SlackUser).filter(
            SlackUser.id == user_id, SlackUser.workspace_id == workspace_id
        ).first()
        if not user:
            return _slack_error("user_not_found")
        existing = db.query(ChannelMember).filter(
            ChannelMember.channel_id == body.channel,
            ChannelMember.user_id == user_id,
        ).first()
        if not existing:
            db.add(ChannelMember(channel_id=body.channel, user_id=user_id))
    db.commit()
    return {
        "ok": True,
        "channel": _channel_to_schema(ch, db),
        "warning": "missing_charset",
        "response_metadata": {"warnings": ["missing_charset"]},
    }


@router.post("/conversations.kick")
def conversations_kick(
    body: ConversationsKickRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")
    membership = db.query(ChannelMember).filter(
        ChannelMember.channel_id == body.channel,
        ChannelMember.user_id == body.user,
    ).first()
    if not membership:
        return _slack_error("not_in_channel")
    db.delete(membership)
    db.commit()
    return {"ok": True, "errors": {}, "warning": "missing_charset", "response_metadata": {"warnings": ["missing_charset"]}}


@router.post("/conversations.join")
def conversations_join(
    body: _ChannelBody,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
    current_user_id: str = Depends(resolve_current_user_id),
    token_type: str = Depends(resolve_token_type),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")
    if ch.is_private:
        return _slack_error("is_private")
    user = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace_id,
        SlackUser.id == current_user_id,
    ).first()
    if user:
        existing = db.query(ChannelMember).filter(
            ChannelMember.channel_id == body.channel,
            ChannelMember.user_id == user.id,
        ).first()
        if not existing:
            db.add(ChannelMember(channel_id=body.channel, user_id=user.id))
            db.commit()
    return {
        "ok": True,
        "channel": _channel_to_schema_create(ch, db, token_type=token_type),
        "warning": "missing_charset",
        "response_metadata": {"warnings": ["missing_charset"]},
    }


@router.post("/conversations.leave")
def conversations_leave(
    body: _ChannelBody,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
    current_user_id: str = Depends(resolve_current_user_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")
    if ch.name == "general":
        return _slack_error("cant_leave_general")
    user = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace_id,
        SlackUser.id == current_user_id,
    ).first()
    if user:
        membership = db.query(ChannelMember).filter(
            ChannelMember.channel_id == body.channel,
            ChannelMember.user_id == user.id,
        ).first()
        if not membership:
            return JSONResponse(content={"ok": False, "not_in_channel": True})
        db.delete(membership)
        db.commit()
    return {"ok": True, "warning": "missing_charset", "response_metadata": {"warnings": ["missing_charset"]}}


@router.get("/conversations.members")
def conversations_members(
    channel: str = Query(...),
    limit: int = Query(200, ge=1, le=1000),
    cursor: str | None = Query(None),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
    current_user_id: str = Depends(resolve_current_user_id),
):
    ch = db.query(Channel).filter(
        Channel.id == channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")
    if ch.is_private and not ch.is_im and not _is_member(ch, db, current_user_id):
        return _slack_error("not_in_channel")

    q = db.query(ChannelMember).filter(ChannelMember.channel_id == channel)

    # Cursor-based pagination: cursor encodes "after:<user_id>"
    if cursor:
        payload = decode_cursor(cursor)
        if payload and payload.startswith("after:"):
            after_uid = payload[len("after:"):]
            q = q.filter(ChannelMember.user_id > after_uid)

    q = q.order_by(ChannelMember.user_id.asc())
    members = q.limit(limit + 1).all()

    has_more = len(members) > limit
    members = members[:limit]

    next_cursor = encode_cursor(f"after:{members[-1].user_id}") if has_more and members else ""
    return ConversationMembersResponse(
        ok=True,
        members=[m.user_id for m in members],
        response_metadata={"next_cursor": next_cursor},
    )


@router.get("/conversations.history")
def conversations_history(
    channel: str = Query(...),
    oldest: str | None = Query(None),
    latest: str | None = Query(None),
    limit: int = Query(20, ge=1, le=1000),
    inclusive: bool = Query(False),
    cursor: str | None = Query(None),
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

    # Only top-level messages (no replies, or messages that ARE the thread parent)
    query = db.query(Message).filter(
        Message.channel_id == channel,
        Message.workspace_id == workspace_id,
    ).filter(
        (Message.thread_ts == None) | (Message.thread_ts == Message.ts)
    )

    # Cursor-based pagination: cursor encodes "next_ts:<ts>", meaning fetch messages older than ts
    if cursor:
        payload = decode_cursor(cursor)
        if payload and payload.startswith("next_ts:"):
            cursor_ts = payload[len("next_ts:"):]
            query = query.filter(Message.ts < cursor_ts)
    elif oldest:
        if inclusive:
            query = query.filter(Message.ts >= oldest)
        else:
            query = query.filter(Message.ts > oldest)

    if latest:
        if inclusive:
            query = query.filter(Message.ts <= latest)
        else:
            query = query.filter(Message.ts < latest)

    # Clamp to 100 per page (real Slack default is 100, max 1000)
    effective_limit = min(limit, 100)

    # Newest first
    messages = query.order_by(Message.ts.desc()).limit(effective_limit + 1).all()

    has_more = len(messages) > effective_limit
    limit = effective_limit
    messages = messages[:limit]

    msg_list = [_message_to_schema(m, team_id=team_id, db=db).model_dump() for m in messages]

    # next_cursor points to the oldest ts in this batch (real Slack format)
    next_cursor = encode_cursor(f"next_ts:{messages[-1].ts}") if has_more and messages else ""

    # Base response — matches conversations_history_empty fixture when empty
    resp: dict = {
        "ok": True,
        "messages": msg_list,
        "has_more": has_more,
        "pin_count": 0,
        "channel_actions_ts": None,
        "channel_actions_count": 0,
    }
    # Only include response_metadata when paginating (matches real Slack behavior)
    if has_more:
        resp["response_metadata"] = {"next_cursor": next_cursor}
    return resp


@router.get("/conversations.replies")
def conversations_replies(
    channel: str = Query(...),
    ts: str = Query(...),
    oldest: str | None = Query(None),
    latest: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    inclusive: bool = Query(True),
    cursor: str | None = Query(None),
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

    # All messages in the thread (thread_ts == ts), including parent
    query = db.query(Message).filter(
        Message.channel_id == channel,
        Message.workspace_id == workspace_id,
        Message.thread_ts == ts,
    )
    # Cursor-based pagination: cursor encodes "next_ts:<ts>", fetch replies after that ts
    if cursor:
        payload = decode_cursor(cursor)
        if payload and payload.startswith("next_ts:"):
            cursor_ts = payload[len("next_ts:"):]
            query = query.filter(Message.ts > cursor_ts)
    else:
        if oldest:
            query = query.filter(Message.ts >= oldest)
        if latest:
            query = query.filter(Message.ts <= latest)

    messages = query.order_by(Message.ts.asc()).limit(limit + 1).all()
    has_more = len(messages) > limit
    messages = messages[:limit]

    next_cursor = encode_cursor(f"next_ts:{messages[-1].ts}") if has_more and messages else ""

    # Compute thread metadata for parent and replies
    parent_msg = messages[0] if messages else None
    replies = messages[1:] if len(messages) > 1 else []
    reply_user_ids = list(dict.fromkeys(r.user_id for r in replies))  # unique, ordered
    latest_reply_ts = replies[-1].ts if replies else None
    parent_user_id = parent_msg.user_id if parent_msg else None

    serialized = []
    for i, m in enumerate(messages):
        if i == 0:
            # Thread parent: include is_locked, subscribed, reply_users, latest_reply
            serialized.append(_message_to_schema(
                m,
                team_id=team_id,
                is_locked=False,
                subscribed=False,
                latest_reply=latest_reply_ts,
                reply_users_count=len(reply_user_ids) if reply_user_ids else None,
                reply_users=reply_user_ids if reply_user_ids else None,
                db=db,
            ).model_dump())
        else:
            # Reply: include parent_user_id
            serialized.append(_message_to_schema(
                m,
                team_id=team_id,
                parent_user_id=parent_user_id,
                db=db,
            ).model_dump())

    result = {
        "ok": True,
        "messages": serialized,
        "has_more": has_more,
    }
    if has_more:
        result["response_metadata"] = {"next_cursor": next_cursor}
    return result


@router.post("/conversations.setPurpose")
def conversations_set_purpose(
    body: ConversationsPurposeRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")
    ch.purpose = body.purpose
    db.commit()
    db.refresh(ch)
    return {
        "ok": True,
        "channel": _channel_to_schema(ch, db),
        "warning": "missing_charset",
        "response_metadata": {"warnings": ["missing_charset"]},
    }


@router.post("/conversations.setTopic")
def conversations_set_topic(
    body: ConversationsTopicRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    ch = db.query(Channel).filter(
        Channel.id == body.channel, Channel.workspace_id == workspace_id
    ).first()
    if not ch:
        return _slack_error("channel_not_found")
    ch.topic = body.topic
    db.commit()
    db.refresh(ch)
    return {
        "ok": True,
        "channel": _channel_to_schema(ch, db),
        "warning": "missing_charset",
        "response_metadata": {"warnings": ["missing_charset"]},
    }
