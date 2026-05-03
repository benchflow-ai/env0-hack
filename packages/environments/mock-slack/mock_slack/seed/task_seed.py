"""Per-task seed scenario for mock-slack.

Each task under tasks/<task-name>/data/needles.py may define:
    SEED_CHANNELS  — list of channel dicts to pre-create
    SEED_MESSAGES  — dict of {channel_name: [message dicts]} to pre-seed
    FILL_CONFIG    — dict with optional keys:
                       base_scenario (str): "default" | "none" (default: "default")

Usage in generator.py:
    seed_task_scenario(db, workspace_id, user_map, channel_map, rng, base_time, task_dir_name)
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

_TASKS_DIR = (
    Path(os.environ["TASKS_DIR"])
    if "TASKS_DIR" in os.environ
    else Path(__file__).resolve().parents[5] / "tasks"
)


def _load_needles(
    task_dir_name: str | None = None,
    task_data_path: str | None = None,
):
    if task_data_path:
        needles_path = Path(task_data_path) / "needles.py"
    else:
        if not task_dir_name:
            raise ValueError("task_dir_name or task_data_path required")
        needles_path = _TASKS_DIR / task_dir_name / "data" / "needles.py"
    if not needles_path.exists():
        raise FileNotFoundError(f"Task needles not found: {needles_path}")

    module_suffix = (
        task_dir_name.replace("-", "_")
        if task_dir_name
        else f"path_{abs(hash(str(needles_path.resolve())))}"
    )
    module_name = f"slack_needles_{module_suffix}"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, needles_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _get_fill_config(
    task_dir_name: str | None = None,
    task_data_path: str | None = None,
) -> dict:
    try:
        mod = _load_needles(task_dir_name=task_dir_name, task_data_path=task_data_path)
        return getattr(mod, "FILL_CONFIG", {})
    except FileNotFoundError:
        return {}


def get_base_scenario(
    task_dir_name: str | None = None,
    task_data_path: str | None = None,
) -> str:
    """Return the base scenario name for a task (default: 'default')."""
    return _get_fill_config(
        task_dir_name=task_dir_name,
        task_data_path=task_data_path,
    ).get("base_scenario", "default")


def get_exclude_channels(
    task_dir_name: str | None = None,
    task_data_path: str | None = None,
) -> set[str]:
    """Return channel names to exclude from default scenario seeding."""
    return set(
        _get_fill_config(
            task_dir_name=task_dir_name,
            task_data_path=task_data_path,
        ).get("exclude_channels", [])
    )


def seed_task_scenario(
    db: Session,
    workspace_id: str,
    user_map: dict[str, str],
    channel_map: dict[str, str],
    rng,
    base_time: datetime,
    task_dir_name: str | None = None,
    task_data_path: str | None = None,
):
    """Inject task-specific channels and messages on top of the base scenario."""
    from mock_slack.models import Channel, ChannelMember, Message, Reaction, SlackUser
    from mock_slack.seed.generator import _make_ts, _make_id

    mod = _load_needles(task_dir_name=task_dir_name, task_data_path=task_data_path)
    seed_users = getattr(mod, "SEED_USERS", [])
    seed_channels = getattr(mod, "SEED_CHANNELS", [])

    # Create task-specific users
    for user_data in seed_users:
        user_id = user_data.get("id") or ("U" + _make_id()[:8].upper())
        db.add(SlackUser(
            id=user_id,
            workspace_id=workspace_id,
            name=user_data["name"],
            real_name=user_data.get("real_name", user_data["name"]),
            email=user_data.get("email", ""),
            title=user_data.get("title", ""),
            is_bot=user_data.get("is_bot", False),
            is_admin=user_data.get("is_admin", False),
        ))
        user_map[user_data["key"]] = user_id

    db.flush()
    seed_messages = getattr(mod, "SEED_MESSAGES", {})

    # Create task-specific channels
    for ch_data in seed_channels:
        ch_id = ch_data.get("id") or ("C" + _make_id()[:8].upper())
        ch = Channel(
            id=ch_id,
            workspace_id=workspace_id,
            name=ch_data["name"].lower().replace(" ", "-"),
            is_private=ch_data.get("is_private", False),
            is_im=ch_data.get("is_im", False),
            creator_id=user_map.get(ch_data.get("creator", "alex"), next(iter(user_map.values()))),
            topic=ch_data.get("topic", ""),
            purpose=ch_data.get("purpose", ""),
            created_at=base_time,
        )
        db.add(ch)
        channel_map[ch_data["name"]] = ch_id

        for member_key in ch_data.get("members", []):
            uid = user_map.get(member_key)
            if uid:
                db.add(ChannelMember(channel_id=ch_id, user_id=uid))

    db.flush()

    # Seed task-specific pins (must come after channels are created)
    from mock_slack.models import Pin
    for ch_data in seed_channels:
        ch_id = ch_data.get("id") or channel_map.get(ch_data["name"])
        if not ch_id:
            continue
        for pin_data in ch_data.get("pins", []):
            from datetime import timedelta
            pin_time = base_time - timedelta(days=pin_data.get("days_ago", 1))
            pin_ts = _make_ts(pin_time)
            pin_sender_id = user_map.get(pin_data.get("pinned_by", "alex"))
            if not pin_sender_id:
                pin_sender_id = next(iter(user_map.values()))
            # Create the message that will be pinned
            pin_msg_id = _make_id()
            db.add(Message(
                id=pin_msg_id,
                channel_id=ch_id,
                workspace_id=workspace_id,
                user_id=pin_sender_id,
                text=pin_data.get("text", ""),
                ts=pin_ts,
                thread_ts=pin_ts,
                is_pinned=True,
                created_at=pin_time,
            ))
            db.flush()
            # Create the pin record
            db.add(Pin(
                id=_make_id(),
                channel_id=ch_id,
                message_id=pin_msg_id,
                user_id=pin_sender_id,
                created_at=pin_time,
            ))

    db.flush()

    # Seed task-specific messages
    for ch_name, msgs in seed_messages.items():
        ch_id = channel_map.get(ch_name)
        if not ch_id:
            continue
        for i, msg_data in enumerate(msgs):
            from datetime import timedelta
            if "days_ago" in msg_data:
                msg_time = base_time - timedelta(days=msg_data["days_ago"])
            else:
                msg_time = base_time - timedelta(hours=len(msgs) - i)
            ts = _make_ts(msg_time, offset_seconds=i * 0.1)
            sender_id = user_map.get(msg_data.get("sender", "alex"))
            if not sender_id:
                continue
            msg_id = _make_id()
            reply_count = len(msg_data.get("thread", []))
            db.add(Message(
                id=msg_id,
                channel_id=ch_id,
                workspace_id=workspace_id,
                user_id=sender_id,
                text=msg_data.get("text", ""),
                ts=ts,
                thread_ts=ts,
                created_at=msg_time,
                reply_count=reply_count,
            ))
            for rxn_data in msg_data.get("reactions", []):
                emoji = rxn_data.get("emoji", "thumbsup")
                for reactor_key in rxn_data.get("users", []):
                    reactor_id = user_map.get(reactor_key)
                    if reactor_id:
                        db.add(Reaction(
                            id=_make_id(),
                            message_id=msg_id,
                            user_id=reactor_id,
                            emoji_name=emoji,
                        ))

            # Seed thread replies
            for j, reply_data in enumerate(msg_data.get("thread", [])):
                reply_time = msg_time + timedelta(minutes=(j + 1) * 3)
                reply_ts = _make_ts(reply_time, offset_seconds=j * 0.01 + 0.001)
                reply_sender_id = user_map.get(reply_data.get("sender", "alex"))
                if not reply_sender_id:
                    continue
                db.add(Message(
                    id=_make_id(),
                    channel_id=ch_id,
                    workspace_id=workspace_id,
                    user_id=reply_sender_id,
                    text=reply_data.get("text", ""),
                    ts=reply_ts,
                    thread_ts=ts,
                    created_at=reply_time,
                ))

    db.flush()

    # Seed invite triggers
    from mock_slack.models import InviteTrigger
    for trigger in getattr(mod, "SEED_INVITE_TRIGGERS", []):
        ch_id = channel_map.get(trigger["grant_channel"])
        uid = user_map.get(trigger["when_dm_to"])
        if ch_id and uid:
            db.add(InviteTrigger(
                workspace_id=workspace_id,
                channel_id=ch_id,
                trigger_user_id=uid,
            ))

    db.flush()
