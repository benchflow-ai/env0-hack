"""State snapshots, reset, and diff functionality."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from sqlalchemy.orm import Session

from mock_slack.models import (
    get_session_factory,
    get_engine,
    Base,
    Workspace,
    SlackUser,
    Channel,
    ChannelMember,
    Message,
    Reaction,
    SlackFile,
    Pin,
    Reminder,
)

SNAPSHOTS_DIR = Path(__file__).resolve().parent.parent.parent / ".data" / "snapshots_slack"


def _serialize_workspace(db: Session, workspace: Workspace) -> dict:
    """Serialize full workspace state."""
    users = db.query(SlackUser).filter(SlackUser.workspace_id == workspace.id).all()
    channels = db.query(Channel).filter(Channel.workspace_id == workspace.id).all()
    messages = db.query(Message).filter(Message.workspace_id == workspace.id).all()
    reactions = db.query(Reaction).filter(
        Reaction.message_id.in_([m.id for m in messages])
    ).all() if messages else []
    files = db.query(SlackFile).filter(SlackFile.workspace_id == workspace.id).all()
    pins_list = []
    for ch in channels:
        ch_pins = db.query(Pin).filter(Pin.channel_id == ch.id).all()
        pins_list.extend(ch_pins)
    reminders = db.query(Reminder).filter(Reminder.workspace_id == workspace.id).all()
    members = db.query(ChannelMember).filter(
        ChannelMember.channel_id.in_([c.id for c in channels])
    ).all() if channels else []

    return {
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "domain": workspace.domain,
            "team_id": workspace.team_id,
        },
        "users": [
            {
                "id": u.id,
                "name": u.name,
                "real_name": u.real_name,
                "email": u.email,
                "title": u.title,
                "is_admin": u.is_admin,
                "is_bot": u.is_bot,
                "is_deleted": u.is_deleted,
                "tz": u.tz,
            }
            for u in users
        ],
        "channels": [
            {
                "id": c.id,
                "name": c.name,
                "is_private": c.is_private,
                "is_archived": c.is_archived,
                "is_im": c.is_im,
                "is_mpim": c.is_mpim,
                "creator_id": c.creator_id,
                "topic": c.topic,
                "purpose": c.purpose,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in channels
        ],
        "channel_members": [
            {"channel_id": m.channel_id, "user_id": m.user_id}
            for m in members
        ],
        "messages": [
            {
                "id": msg.id,
                "channel_id": msg.channel_id,
                "user_id": msg.user_id,
                "text": msg.text,
                "ts": msg.ts,
                "thread_ts": msg.thread_ts,
                "is_edited": msg.is_edited,
                "edited_ts": msg.edited_ts,
                "reply_count": msg.reply_count,
                "is_pinned": msg.is_pinned,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in messages
        ],
        "reactions": [
            {
                "id": r.id,
                "message_id": r.message_id,
                "user_id": r.user_id,
                "emoji_name": r.emoji_name,
            }
            for r in reactions
        ],
        "files": [
            {
                "id": f.id,
                "user_id": f.user_id,
                "name": f.name,
                "title": f.title,
                "mimetype": f.mimetype,
                "filetype": f.filetype,
                "size": f.size,
                "is_public": f.is_public,
                "channel_id": f.channel_id,
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "content": f.content,
            }
            for f in files
        ],
        "pins": [
            {
                "id": p.id,
                "channel_id": p.channel_id,
                "message_id": p.message_id,
                "user_id": p.user_id,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in pins_list
        ],
        "reminders": [
            {
                "id": r.id,
                "creator_id": r.creator_id,
                "user_id": r.user_id,
                "text": r.text,
                "remind_at": r.remind_at.isoformat() if r.remind_at else None,
                "is_complete": r.is_complete,
                "complete_ts": r.complete_ts,
            }
            for r in reminders
        ],
    }


def get_state_dump() -> dict:
    """Get full state dump for all workspaces."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        workspaces = db.query(Workspace).all()
        return {
            "workspaces": {w.id: _serialize_workspace(db, w) for w in workspaces},
            "timestamp": datetime.utcnow().isoformat(),
        }
    finally:
        db.close()


def take_snapshot(name: str) -> Path:
    """Save current state to a JSON snapshot."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    state = get_state_dump()
    path = SNAPSHOTS_DIR / f"{name}.json"
    path.write_text(json.dumps(state, indent=2))
    return path


def restore_snapshot(name: str) -> bool:
    """Restore DB from a snapshot. Returns True if successful."""
    path = SNAPSHOTS_DIR / f"{name}.json"
    if not path.exists():
        return False

    state = json.loads(path.read_text())
    _restore_from_state(state)
    return True


def _restore_from_state(state: dict):
    """Rebuild DB from a state dict."""
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        for ws_id, ws_data in state.get("workspaces", {}).items():
            w = ws_data["workspace"]
            db.add(Workspace(
                id=w["id"],
                name=w["name"],
                domain=w.get("domain", ""),
                team_id=w.get("team_id", ""),
            ))

            for u in ws_data.get("users", []):
                db.add(SlackUser(
                    id=u["id"],
                    workspace_id=ws_id,
                    name=u.get("name", ""),
                    real_name=u.get("real_name", ""),
                    email=u.get("email", ""),
                    title=u.get("title", ""),
                    is_admin=u.get("is_admin", False),
                    is_bot=u.get("is_bot", False),
                    is_deleted=u.get("is_deleted", False),
                    tz=u.get("tz", "America/Los_Angeles"),
                ))

            for c in ws_data.get("channels", []):
                created_at = None
                if c.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(c["created_at"])
                    except (ValueError, TypeError):
                        created_at = datetime.utcnow()
                db.add(Channel(
                    id=c["id"],
                    workspace_id=ws_id,
                    name=c.get("name", ""),
                    is_private=c.get("is_private", False),
                    is_archived=c.get("is_archived", False),
                    is_im=c.get("is_im", False),
                    is_mpim=c.get("is_mpim", False),
                    creator_id=c.get("creator_id", ""),
                    topic=c.get("topic", ""),
                    purpose=c.get("purpose", ""),
                    created_at=created_at or datetime.utcnow(),
                ))

            for cm in ws_data.get("channel_members", []):
                db.add(ChannelMember(
                    channel_id=cm["channel_id"],
                    user_id=cm["user_id"],
                ))

            for msg in ws_data.get("messages", []):
                created_at = None
                if msg.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(msg["created_at"])
                    except (ValueError, TypeError):
                        created_at = datetime.utcnow()
                db.add(Message(
                    id=msg["id"],
                    channel_id=msg["channel_id"],
                    workspace_id=ws_id,
                    user_id=msg["user_id"],
                    text=msg.get("text", ""),
                    ts=msg["ts"],
                    thread_ts=msg.get("thread_ts"),
                    is_edited=msg.get("is_edited", False),
                    edited_ts=msg.get("edited_ts"),
                    reply_count=msg.get("reply_count", 0),
                    is_pinned=msg.get("is_pinned", False),
                    created_at=created_at or datetime.utcnow(),
                ))

            for r in ws_data.get("reactions", []):
                db.add(Reaction(
                    id=r["id"],
                    message_id=r["message_id"],
                    user_id=r["user_id"],
                    emoji_name=r["emoji_name"],
                ))

            for f in ws_data.get("files", []):
                created_at = None
                if f.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(f["created_at"])
                    except (ValueError, TypeError):
                        created_at = datetime.utcnow()
                db.add(SlackFile(
                    id=f["id"],
                    workspace_id=ws_id,
                    user_id=f["user_id"],
                    name=f.get("name", ""),
                    title=f.get("title", ""),
                    mimetype=f.get("mimetype", "text/plain"),
                    filetype=f.get("filetype", "text"),
                    size=f.get("size", 0),
                    is_public=f.get("is_public", False),
                    channel_id=f.get("channel_id"),
                    created_at=created_at or datetime.utcnow(),
                    content=f.get("content", ""),
                ))

            for p in ws_data.get("pins", []):
                created_at = None
                if p.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(p["created_at"])
                    except (ValueError, TypeError):
                        created_at = datetime.utcnow()
                db.add(Pin(
                    id=p["id"],
                    channel_id=p["channel_id"],
                    message_id=p["message_id"],
                    user_id=p["user_id"],
                    created_at=created_at or datetime.utcnow(),
                ))

            for rem in ws_data.get("reminders", []):
                remind_at = None
                if rem.get("remind_at"):
                    try:
                        remind_at = datetime.fromisoformat(rem["remind_at"])
                    except (ValueError, TypeError):
                        remind_at = datetime.utcnow()
                db.add(Reminder(
                    id=rem["id"],
                    workspace_id=ws_id,
                    creator_id=rem["creator_id"],
                    user_id=rem["user_id"],
                    text=rem.get("text", ""),
                    remind_at=remind_at or datetime.utcnow(),
                    is_complete=rem.get("is_complete", False),
                    complete_ts=rem.get("complete_ts"),
                ))

        db.commit()
    finally:
        db.close()


def get_diff(initial_state: dict | None = None) -> dict:
    """Compute diff between initial state (snapshot) and current state."""
    current = get_state_dump()

    if initial_state is None:
        path = SNAPSHOTS_DIR / "initial.json"
        if path.exists():
            initial_state = json.loads(path.read_text())
        else:
            return {"error": "No initial snapshot found"}

    diff = {"added": {}, "updated": {}, "deleted": {}}

    for ws_id, current_ws in current.get("workspaces", {}).items():
        initial_ws = initial_state.get("workspaces", {}).get(ws_id)
        if not initial_ws:
            diff["added"][ws_id] = current_ws
            continue

        # Compare messages by ts
        curr_msgs = {m["ts"]: m for m in current_ws.get("messages", [])}
        init_msgs = {m["ts"]: m for m in initial_ws.get("messages", [])}

        ws_diff = {"messages": {"added": [], "updated": [], "deleted": []}}

        for ts, msg in curr_msgs.items():
            if ts not in init_msgs:
                ws_diff["messages"]["added"].append(msg)
            elif msg != init_msgs[ts]:
                changes = {}
                for k, v in msg.items():
                    if init_msgs[ts].get(k) != v:
                        changes[k] = v
                ws_diff["messages"]["updated"].append({"ts": ts, **changes})

        for ts in init_msgs:
            if ts not in curr_msgs:
                ws_diff["messages"]["deleted"].append({"ts": ts})

        # Compare channels
        curr_channels = {c["id"]: c for c in current_ws.get("channels", [])}
        init_channels = {c["id"]: c for c in initial_ws.get("channels", [])}
        ws_diff["channels"] = {"added": [], "updated": [], "deleted": []}
        for cid, ch in curr_channels.items():
            if cid not in init_channels:
                ws_diff["channels"]["added"].append(ch)
            elif ch != init_channels[cid]:
                ws_diff["channels"]["updated"].append(ch)
        for cid in init_channels:
            if cid not in curr_channels:
                ws_diff["channels"]["deleted"].append({"id": cid})

        # Compare reactions
        curr_rxns = {r["id"]: r for r in current_ws.get("reactions", [])}
        init_rxns = {r["id"]: r for r in initial_ws.get("reactions", [])}
        ws_diff["reactions"] = {"added": [], "deleted": []}
        for rid, rxn in curr_rxns.items():
            if rid not in init_rxns:
                ws_diff["reactions"]["added"].append(rxn)
        for rid in init_rxns:
            if rid not in curr_rxns:
                ws_diff["reactions"]["deleted"].append({"id": rid})

        # Compare channel_members
        curr_members = {(m["channel_id"], m["user_id"]) for m in current_ws.get("channel_members", [])}
        init_members = {(m["channel_id"], m["user_id"]) for m in initial_ws.get("channel_members", [])}
        ws_diff["channel_members"] = {
            "added": [{"channel_id": c, "user_id": u} for c, u in curr_members - init_members],
            "deleted": [{"channel_id": c, "user_id": u} for c, u in init_members - curr_members],
        }

        if any(
            any(v) for v in ws_diff["messages"].values()
        ) or any(
            any(v) for v in ws_diff.get("channels", {}).values()
        ) or any(
            any(v) for v in ws_diff.get("reactions", {}).values()
        ) or any(
            any(v) for v in ws_diff.get("channel_members", {}).values()
        ):
            diff["updated"][ws_id] = ws_diff

    return diff
