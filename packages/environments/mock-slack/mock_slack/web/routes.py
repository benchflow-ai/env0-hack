"""Web UI routes — Slack-like interface using Jinja2 + HTMX."""

from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from sqlalchemy.orm import Session

from mock_slack.models import Workspace, SlackUser, Channel, Message, ChannelMember
from mock_slack.models import SlackFile, Reaction, Pin, Reminder
from mock_slack.api.deps import get_db

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _get_dm_names(db: Session, channels: list, current_user_id: str) -> dict:
    """Return {channel_id: display_name} for all IM channels in the list."""
    dm_channels = [c for c in channels if getattr(c, "is_im", False)]
    if not dm_channels:
        return {}
    dm_channel_ids = [c.id for c in dm_channels]

    # Primary: look up via ChannelMember → SlackUser (excludes current user)
    rows = (
        db.query(ChannelMember.channel_id, SlackUser.real_name, SlackUser.name)
        .join(SlackUser, SlackUser.id == ChannelMember.user_id)
        .filter(
            ChannelMember.channel_id.in_(dm_channel_ids),
            ChannelMember.user_id != current_user_id,
        )
        .all()
    )
    result = {row.channel_id: row.real_name or row.name for row in rows}

    # Fallback: for channels without a member record, parse channel.name
    # Formats: "dm-alex-priya", "dm-U06NINAWOOD", "dm-userid1-userid2"
    missing = [c for c in dm_channels if c.id not in result]
    if missing:
        all_users = list(db.query(SlackUser).filter(
            SlackUser.workspace_id == dm_channels[0].workspace_id
        ).all())
        user_by_id = {u.id: u for u in all_users}
        for ch in missing:
            name = ch.name or ""
            # Strip leading "dm-" then split remaining parts
            remainder = name[3:] if name.startswith("dm-") else name
            parts = remainder.split("-")
            found = None
            for part in parts:
                if not part:
                    continue
                # Try as direct user ID (e.g. "U06NINAWOOD")
                candidate = user_by_id.get(part) or user_by_id.get(part.upper())
                if candidate and candidate.id != current_user_id:
                    found = candidate.real_name or candidate.name
                    break
                # Try as name substring (e.g. "alex" matches "Alex Chen")
                part_lower = part.lower()
                for u in all_users:
                    if u.id == current_user_id:
                        continue
                    uname = (u.real_name or u.name or "").lower()
                    if part_lower in uname:
                        found = u.real_name or u.name
                        break
                if found:
                    break
            if found:
                result[ch.id] = found

    return result


def _get_dm_users(db: Session, channels: list, current_user_id: str) -> dict:
    """Return {channel_id: SlackUser} for DM channels, keyed by the other participant."""
    dm_channels = [c for c in channels if getattr(c, "is_im", False)]
    if not dm_channels:
        return {}

    dm_channel_ids = [c.id for c in dm_channels]
    rows = (
        db.query(ChannelMember.channel_id, SlackUser)
        .join(SlackUser, SlackUser.id == ChannelMember.user_id)
        .filter(
            ChannelMember.channel_id.in_(dm_channel_ids),
            ChannelMember.user_id != current_user_id,
        )
        .all()
    )
    result = {channel_id: user for channel_id, user in rows}

    missing = [c for c in dm_channels if c.id not in result]
    if missing:
        all_users = list(db.query(SlackUser).filter(
            SlackUser.workspace_id == dm_channels[0].workspace_id
        ).all())
        user_by_id = {u.id: u for u in all_users}
        for ch in missing:
            name = ch.name or ""
            remainder = name[3:] if name.startswith("dm-") else name
            parts = remainder.split("-")
            found = None
            for part in parts:
                if not part:
                    continue
                candidate = user_by_id.get(part) or user_by_id.get(part.upper())
                if candidate and candidate.id != current_user_id:
                    found = candidate
                    break
                part_lower = part.lower()
                for u in all_users:
                    if u.id == current_user_id:
                        continue
                    uname = (u.real_name or u.name or "").lower()
                    if part_lower in uname:
                        found = u
                        break
                if found:
                    break
            if found:
                result[ch.id] = found

    return result


def _dedup_dm_channels(db: Session, channels: list, current_user_id: str) -> list:
    """Return deduplicated DM channels — one per other-user pair.

    Duplicates are eliminated at the DB level by _get_or_create_dm_channel,
    but this provides a safety net in case stale data is still in the list.
    """
    dm_channels = [c for c in channels if getattr(c, "is_im", False) and not getattr(c, "is_mpim", False)]
    if not dm_channels:
        return []

    channel_ids = [c.id for c in dm_channels]
    rows = (
        db.query(ChannelMember.channel_id, ChannelMember.user_id)
        .filter(
            ChannelMember.channel_id.in_(channel_ids),
            ChannelMember.user_id != current_user_id,
        )
        .all()
    )
    channel_to_other: dict[str, str] = {r.channel_id: r.user_id for r in rows}

    seen_users: set[str] = set()
    result = []
    for ch in dm_channels:
        other_id = channel_to_other.get(ch.id)
        if other_id is None or other_id in seen_users:
            continue
        seen_users.add(other_id)
        result.append(ch)
    return result


def _get_workspace_channels(db: Session, workspace_id: str, current_user_id: str) -> list:
    """Fetch workspace channels with DMs deduplicated (one per user pair)."""
    all_channels = db.query(Channel).filter(Channel.workspace_id == workspace_id).all()
    non_dm = [c for c in all_channels if not getattr(c, "is_im", False) and not getattr(c, "is_mpim", False)]
    deduped_dms = _dedup_dm_channels(db, all_channels, current_user_id)
    return non_dm + deduped_dms


def _get_dev_db_stats(db: Session, workspace_id: str) -> dict:
    return {
        "messages": db.query(Message).filter(Message.workspace_id == workspace_id).count(),
        "channels": db.query(Channel).filter(Channel.workspace_id == workspace_id).count(),
        "users": db.query(SlackUser).filter(SlackUser.workspace_id == workspace_id).count(),
        "files": db.query(SlackFile).filter(SlackFile.workspace_id == workspace_id).count(),
    }


def _get_test_inventory() -> dict:
    tests_dir = _PROJECT_ROOT / "tests"
    inventory = {}
    total = 0
    if not tests_dir.exists():
        return {"files": {}, "total": 0}
    for test_file in sorted(tests_dir.glob("test_*.py")):
        filename = test_file.name
        content = test_file.read_text()
        classes: dict[str, list] = {}
        current_class = None
        file_count = 0
        for line in content.splitlines():
            class_match = re.match(r"^class (Test\w+)", line)
            if class_match:
                current_class = class_match.group(1)
                classes[current_class] = []
            test_match = re.match(r"    def (test_\w+)", line)
            if test_match and current_class:
                classes[current_class].append(test_match.group(1))
                file_count += 1
        inventory[filename] = {"classes": classes, "count": file_count}
        total += file_count
    return {"files": inventory, "total": total}


def _run_pytest() -> dict | None:
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "--tb=short", "-q",
             "--json-report", "--json-report-file=-"],
            capture_output=True, text=True, timeout=120,
            cwd=str(_PROJECT_ROOT),
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        try:
            return json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _parse_test_results(report: dict) -> dict:
    tests = report.get("tests", [])
    summary = report.get("summary", {})
    grouped: dict[str, dict] = {}
    for t in tests:
        nodeid = t.get("nodeid", "")
        filename = nodeid.split("::")[0] if "::" in nodeid else nodeid
        testname = nodeid.split("::")[-1] if "::" in nodeid else nodeid
        outcome = t.get("outcome", "unknown")
        duration = t.get("duration", 0)
        longrepr = ""
        if outcome == "failed":
            longrepr = t.get("call", {}).get("longrepr", "")
        if filename not in grouped:
            grouped[filename] = {"tests": [], "passed": 0, "failed": 0, "skipped": 0}
        grouped[filename]["tests"].append({
            "name": testname, "outcome": outcome,
            "duration": round(duration, 3), "longrepr": longrepr,
        })
        grouped[filename][outcome if outcome in ("passed", "failed", "skipped") else "skipped"] += 1
    return {
        "total": summary.get("total", len(tests)),
        "passed": summary.get("passed", 0),
        "failed": summary.get("failed", 0),
        "skipped": summary.get("skipped", 0),
        "duration": round(report.get("duration", 0), 2),
        "grouped": grouped,
    }


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_COMMON_REACTION_EMOJIS = [
    "+1",
    "-1",
    "heart",
    "laugh",
    "tada",
    "rocket",
    "eyes",
    "fire",
    "clap",
    "raised_hands",
    "pray",
    "muscle",
]

_EMOJI_GLYPHS = {
    "+1": "👍",
    "-1": "👎",
    "art": "🎨",
    "books": "📚",
    "chart_with_upwards_trend": "📈",
    "clap": "👏",
    "db_postgres": "🐘",
    "eyes": "👀",
    "face_palm": "🤦",
    "fire": "🔥",
    "heart": "❤️",
    "laugh": "😂",
    "muscle": "💪",
    "nerd_face": "🤓",
    "pray": "🙏",
    "raised_hands": "🙌",
    "rocket": "🚀",
    "rotating_light": "🚨",
    "ship": "🚢",
    "tada": "🎉",
    "thumbsup": "👍",
    "trophy": "🏆",
    "white_check_mark": "✅",
    "zap": "⚡",
}


def _slack_emoji_glyph(name: str | None) -> str:
    if not name:
        return "🙂"
    return _EMOJI_GLYPHS.get(name, f":{name}:")


_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_TITLE_CLEANUP_RE = re.compile(r"[-_]+")
_RICH_TEXT_TOKEN_RE = re.compile(
    r"<(?P<slack_url>https?://[^|>\s]+)(?:\|(?P<slack_label>[^>]+))?>"
    r"|(?P<plain_url>https?://[^\s<>()|>]+)"
    r"|:(?P<emoji_name>[a-z0-9_+\-]+):"
)


def _extract_first_url(text: str | None) -> str | None:
    if not text:
        return None
    for match in _RICH_TEXT_TOKEN_RE.finditer(text):
        slack_url = match.group("slack_url")
        if slack_url:
            return slack_url
        plain_url = match.group("plain_url")
        if plain_url:
            return plain_url.rstrip(".,)")
    return None


def _slack_render_link(url: str, label: str | None = None) -> Markup:
    link_label = label or url
    return Markup('<a href="{0}" target="_blank" rel="noopener noreferrer">{1}</a>').format(
        url,
        link_label,
    )


def _slack_render_emoji_token(name: str) -> Markup:
    glyph = _EMOJI_GLYPHS.get(name)
    if not glyph:
        return escape(f":{name}:")
    return Markup('<span class="slack-inline-emoji" title="{0}">{1}</span>').format(
        name.replace("_", " "),
        glyph,
    )


def _slack_render_plain_text_segment(text: str) -> Markup:
    if not text:
        return Markup("")

    rendered_parts: list[Markup | str] = []
    cursor = 0
    for match in _RICH_TEXT_TOKEN_RE.finditer(text):
        start, end = match.span()
        if start > cursor:
            rendered_parts.append(escape(text[cursor:start]))

        slack_url = match.group("slack_url")
        plain_url = match.group("plain_url")
        emoji_name = match.group("emoji_name")
        if slack_url:
            rendered_parts.append(_slack_render_link(slack_url, match.group("slack_label")))
        elif plain_url:
            normalized_url = plain_url.rstrip(".,)")
            trailing = plain_url[len(normalized_url):]
            rendered_parts.append(_slack_render_link(normalized_url))
            if trailing:
                rendered_parts.append(escape(trailing))
        elif emoji_name:
            rendered_parts.append(_slack_render_emoji_token(emoji_name))

        cursor = end

    if cursor < len(text):
        rendered_parts.append(escape(text[cursor:]))

    return Markup("").join(rendered_parts)


def _slack_render_message_text(text: str | None) -> Markup:
    if not text:
        return Markup("")

    rendered_parts: list[Markup | str] = []
    cursor = 0
    for match in _INLINE_CODE_RE.finditer(text):
        start, end = match.span()
        if start > cursor:
            rendered_parts.append(_slack_render_plain_text_segment(text[cursor:start]))
        rendered_parts.append(
            Markup('<code class="slack-inline-code">{0}</code>').format(match.group(1))
        )
        cursor = end

    if cursor < len(text):
        rendered_parts.append(_slack_render_plain_text_segment(text[cursor:]))

    return Markup("").join(rendered_parts)


def _build_link_preview(text: str | None) -> dict | None:
    url = _extract_first_url(text)
    if not url:
        return None

    parsed = urlparse(url)
    domain = (parsed.netloc or "").removeprefix("www.")
    path_parts = [part for part in parsed.path.split("/") if part]
    title_source = path_parts[-1] if path_parts else domain
    title = _TITLE_CLEANUP_RE.sub(" ", title_source).strip() or domain or url
    title = title[:1].upper() + title[1:] if title else domain
    description = (text or "").replace(url, "").strip()

    return {
        "url": url,
        "domain": domain,
        "title": title,
        "description": description,
        "display_path": parsed.path or "/",
    }


def _slack_ordinal(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def _slack_calendar_label(value: datetime) -> str:
    return f"{value.strftime('%b')} {value.day}{_slack_ordinal(value.day)}, {value.year}"


def _slack_relative_time_label(value: datetime, now: datetime) -> str:
    day_delta = max(0, (now.date() - value.date()).days)
    if day_delta == 0:
        return "today"
    if day_delta == 1:
        return "yesterday"
    if day_delta < 7:
        return f"{day_delta} days ago"
    if day_delta < 30:
        weeks = max(1, day_delta // 7)
        unit = "week" if weeks == 1 else "weeks"
        return f"{weeks} {unit} ago"
    if day_delta < 365:
        months = max(1, day_delta // 30)
        unit = "month" if months == 1 else "months"
        return f"{months} {unit} ago"
    years = max(1, day_delta // 365)
    unit = "year" if years == 1 else "years"
    return f"{years} {unit} ago"


def _slack_message_datetime(message: Message | None) -> datetime | None:
    if message is None:
        return None
    created_at = getattr(message, "created_at", None)
    if isinstance(created_at, datetime):
        return created_at
    ts = getattr(message, "ts", None)
    if ts is None:
        return None
    try:
        return datetime.utcfromtimestamp(float(ts))
    except (TypeError, ValueError):
        return None


def _slack_is_message_continuation(
    prev_msg: Message | None,
    msg: Message | None,
    *,
    window_minutes: int = 5,
) -> bool:
    if not prev_msg or not msg:
        return False
    prev_user = getattr(prev_msg, "user", None)
    current_user = getattr(msg, "user", None)
    if not prev_user or not current_user or prev_user.id != current_user.id:
        return False

    prev_time = _slack_message_datetime(prev_msg)
    current_time = _slack_message_datetime(msg)
    if prev_time is None or current_time is None:
        return True
    if current_time.date() != prev_time.date():
        return False
    return timedelta(0) <= (current_time - prev_time) <= timedelta(minutes=window_minutes)


def _slack_date_divider_label(value: datetime | None, *, now: datetime | None = None) -> str:
    if value is None:
        return ""
    now = now or datetime.utcnow()
    if value.date() == now.date():
        return "Today"
    if value.date() == (now.date() - timedelta(days=1)):
        return "Yesterday"
    return _slack_calendar_label(value)


def _slack_reply_summary_label(value: datetime | None, *, now: datetime | None = None) -> str:
    if value is None:
        return ""
    now = now or datetime.utcnow()
    return f"Last reply {_slack_relative_time_label(value, now)}"


templates.env.globals["common_reaction_emojis"] = _COMMON_REACTION_EMOJIS
templates.env.globals["slack_emoji_glyph"] = _slack_emoji_glyph
templates.env.globals["slack_build_link_preview"] = _build_link_preview
templates.env.globals["slack_date_divider_label"] = _slack_date_divider_label
templates.env.globals["slack_reply_summary_label"] = _slack_reply_summary_label
templates.env.globals["slack_is_message_continuation"] = _slack_is_message_continuation
templates.env.globals["slack_render_message_text"] = _slack_render_message_text

def _get_current_workspace_and_user(db: Session, request: Request) -> tuple[Workspace, SlackUser]:
    # Mocking a fixed workspace and user for now or checking headers/cookies
    # Fallback to first workspace and its first non-bot user
    workspace = db.query(Workspace).first()
    user = None
    if workspace:
        user = db.query(SlackUser).filter(
            SlackUser.workspace_id == workspace.id,
            ~SlackUser.is_bot,
            SlackUser.email != "",
        ).first()
    return workspace, user


def _make_slack_ts() -> str:
    return f"{time.time():.6f}"


def _create_message(
    db: Session,
    *,
    workspace_id: str,
    channel_id: str,
    user_id: str,
    text: str,
    thread_ts: str | None = None,
    attachments: list | None = None,
) -> Message:
    now = datetime.utcnow()
    ts = _make_slack_ts()
    root_thread_ts = thread_ts or ts
    msg = Message(
        id=uuid.uuid4().hex,
        channel_id=channel_id,
        workspace_id=workspace_id,
        user_id=user_id,
        text=text,
        ts=ts,
        thread_ts=root_thread_ts,
        attachments=attachments,
        created_at=now,
    )
    db.add(msg)

    if thread_ts:
        parent = db.query(Message).filter(
            Message.channel_id == channel_id,
            Message.ts == thread_ts,
        ).first()
        if parent:
            parent.reply_count = (parent.reply_count or 0) + 1

    db.commit()
    db.refresh(msg)
    return msg


def _get_or_create_dm_channel(
    db: Session,
    *,
    workspace_id: str,
    current_user: SlackUser,
    other_user: SlackUser,
) -> Channel:
    member_ids = sorted({current_user.id, other_user.id})

    candidate_channels = db.query(Channel).filter(
        Channel.workspace_id == workspace_id,
        Channel.is_im == True,
        Channel.is_mpim == False,
    ).all()

    # Collect all matching channels; return the oldest (canonical) one so it
    # always agrees with _dedup_dm_channels and messages never go to a shadow channel.
    matching = []
    for channel in candidate_channels:
        members = sorted(
            member.user_id
            for member in db.query(ChannelMember).filter(ChannelMember.channel_id == channel.id).all()
        )
        if members == member_ids:
            matching.append(channel)

    if matching:
        # Keep the oldest channel; merge all messages from duplicates into it, then delete duplicates
        canonical = min(matching, key=lambda c: c.created_at or c.id)
        for dup in matching:
            if dup.id == canonical.id:
                continue
            # Move messages and thread replies to canonical channel
            db.query(Message).filter(Message.channel_id == dup.id).update(
                {Message.channel_id: canonical.id}, synchronize_session=False
            )
            # Remove duplicate channel members and channel
            db.query(ChannelMember).filter(ChannelMember.channel_id == dup.id).delete(synchronize_session=False)
            db.delete(dup)
        db.commit()
        return canonical

    channel = Channel(
        id="D" + uuid.uuid4().hex[:8].upper(),
        workspace_id=workspace_id,
        name=other_user.real_name or other_user.name,
        is_private=True,
        is_im=True,
        creator_id=current_user.id,
        created_at=datetime.utcnow(),
    )
    db.add(channel)
    for user_id in member_ids:
        db.add(ChannelMember(channel_id=channel.id, user_id=user_id))
    db.commit()
    db.refresh(channel)
    return channel


def _resolve_compose_target(
    db: Session,
    *,
    workspace: Workspace,
    current_user: SlackUser,
    target: str,
) -> tuple[Channel | None, str | None]:
    normalized = (target or "").strip()
    if not normalized:
        return None, "Choose a channel or person to message."

    lowered = normalized.lower()
    bare = lowered[1:] if lowered[:1] in {"#", "@"} else lowered

    channels = db.query(Channel).filter(Channel.workspace_id == workspace.id).all()
    for channel in channels:
        channel_name = (channel.name or "").strip().lower()
        if lowered == channel.id.lower() or lowered == f"#{channel_name}" or bare == channel_name:
            return channel, None

    users = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace.id,
        SlackUser.is_bot == False,
        SlackUser.is_deleted == False,
    ).all()
    for candidate in users:
        matches = {
            candidate.id.lower(),
            candidate.name.lower(),
            f"@{candidate.name.lower()}",
            candidate.real_name.lower(),
            candidate.email.lower(),
        }
        if lowered in matches or bare in matches:
            if candidate.id == current_user.id:
                return None, "Choose another person or channel."
            return _get_or_create_dm_channel(
                db,
                workspace_id=workspace.id,
                current_user=current_user,
                other_user=candidate,
            ), None

    return None, f'Could not find "{normalized}". Use #channel, @user, or an email address.'


def _new_message_context(
    request: Request,
    db: Session,
    *,
    workspace: Workspace | None,
    user: SlackUser | None,
    compose_target: str = "",
    compose_text: str = "",
    compose_error: str | None = None,
) -> dict:
    channels = db.query(Channel).filter(Channel.workspace_id == workspace.id).all() if workspace else []
    users = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace.id,
        SlackUser.is_deleted == False,
        SlackUser.is_bot == False,
    ).all() if workspace else []
    deduped_dms = _dedup_dm_channels(db, channels, user.id) if user else []
    # Replace DM channels in the sidebar channels list with deduplicated ones
    non_dm = [c for c in channels if not getattr(c, "is_im", False) and not getattr(c, "is_mpim", False)]
    sidebar_channels = non_dm + deduped_dms
    return {
        "request": request,
        "workspace": workspace,
        "user": user,
        "channels": sidebar_channels,
        "users": users,
        "compose_target": compose_target,
        "compose_text": compose_text,
        "compose_error": compose_error,
        "has_unread_threads": True,
        "dm_names": _get_dm_names(db, sidebar_channels, user.id) if user else {},
        "dm_users": _get_dm_users(db, sidebar_channels, user.id) if user else {},
    }


def _resolve_dm_footer_name(
    db: Session,
    *,
    workspace_id: str,
    current_user_id: str,
    raw_channel_name: str,
) -> str | None:
    normalized = (raw_channel_name or "").strip()
    if not normalized.lower().startswith("dm-"):
        return None

    dm_channel = next(
        (
            channel
            for channel in db.query(Channel).filter(
                Channel.workspace_id == workspace_id,
                Channel.is_im == True,
                Channel.is_mpim == False,
            ).all()
            if (channel.name or "").strip().lower() == normalized.lower()
        ),
        None,
    )
    if not dm_channel:
        return None

    dm_names = _get_dm_names(db, [dm_channel], current_user_id)
    return dm_names.get(dm_channel.id)


def _normalize_attachment_footer(
    db: Session,
    *,
    workspace_id: str,
    current_user_id: str,
    footer: str | None,
) -> str | None:
    if not footer or "dm-" not in footer.lower():
        return footer

    main, separator, suffix = footer.partition(" · ")
    prefix = ""
    raw_name = main.strip()
    for candidate in ("🔒", "#", "@"):
        if raw_name.startswith(candidate):
            prefix = candidate
            raw_name = raw_name[len(candidate):].strip()
            break

    resolved_name = _resolve_dm_footer_name(
        db,
        workspace_id=workspace_id,
        current_user_id=current_user_id,
        raw_channel_name=raw_name,
    )
    if not resolved_name:
        return footer

    normalized_main = f"@{resolved_name}"
    if separator:
        return f"{normalized_main} · {suffix}"
    return normalized_main


def _normalize_message_attachment_footers(
    db: Session,
    *,
    workspace_id: str,
    current_user_id: str,
    messages: list[Message],
) -> None:
    for msg in messages:
        if not msg.attachments:
            continue
        normalized_attachments = []
        changed = False
        for attachment in msg.attachments:
            if not isinstance(attachment, dict):
                normalized_attachments.append(attachment)
                continue
            updated_attachment = dict(attachment)
            normalized_footer = _normalize_attachment_footer(
                db,
                workspace_id=workspace_id,
                current_user_id=current_user_id,
                footer=updated_attachment.get("footer"),
            )
            if normalized_footer != updated_attachment.get("footer"):
                updated_attachment["footer"] = normalized_footer
                changed = True
            normalized_attachments.append(updated_attachment)
        if changed:
            msg.attachments = normalized_attachments


def _build_thread_preview_maps(
    db: Session,
    *,
    channel_id: str,
    parent_messages: list[Message],
) -> tuple[dict, dict]:
    parent_ts_list = [m.ts for m in parent_messages if m.reply_count and m.reply_count > 0]
    if not parent_ts_list:
        return {}, {}

    # Single query for all replies across all threads (newest first)
    all_replies = (
        db.query(Message)
        .filter(
            Message.channel_id == channel_id,
            Message.thread_ts.in_(parent_ts_list),
            Message.ts != Message.thread_ts,
        )
        .order_by(Message.created_at.desc())
        .all()
    )

    # Group by thread and extract preview data in one pass
    preview_users: dict[str, list[SlackUser]] = {}
    latest_reply_at: dict[str, datetime] = {}
    seen_user_ids: dict[str, set] = {}

    for reply in all_replies:
        thread_ts = reply.thread_ts
        # Track latest reply time (first seen per thread since ordered desc)
        if thread_ts not in latest_reply_at:
            latest_reply_at[thread_ts] = reply.created_at or datetime.utcnow()
        # Collect up to 3 unique users per thread
        if thread_ts not in seen_user_ids:
            seen_user_ids[thread_ts] = set()
        if not reply.user or reply.user.id in seen_user_ids[thread_ts]:
            continue
        if len(seen_user_ids[thread_ts]) >= 3:
            continue
        seen_user_ids[thread_ts].add(reply.user.id)
        preview_users.setdefault(thread_ts, []).append(reply.user)

    return preview_users, latest_reply_at


def _render_new_message_inline(
    request: Request,
    db: Session,
    *,
    workspace: Workspace | None,
    user: SlackUser | None,
    compose_target: str = "",
    compose_text: str = "",
    compose_error: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "new_message_inline.html",
        _new_message_context(
            request,
            db,
            workspace=workspace,
            user=user,
            compose_target=compose_target,
            compose_text=compose_text,
            compose_error=compose_error,
        ),
        status_code=status_code,
    )

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return HTMLResponse("No workspace or user found in DB. Please run seed script.", status_code=404)

    channels = _get_workspace_channels(db, workspace.id, user.id)
    non_dm = [c for c in channels if not getattr(c, "is_im", False)]
    current_channel = non_dm[0] if non_dm else (channels[0] if channels else None)

    return templates.TemplateResponse(request, "dashboard.html", context={
        "workspace": workspace,
        "user": user,
        "channels": channels,
        "current_channel": current_channel, "has_unread_threads": True,
        "dm_names": _get_dm_names(db, channels, user.id) if user else {},
        "dm_users": _get_dm_users(db, channels, user.id) if user else {},
    })

@router.get("/dms", response_class=HTMLResponse)
async def view_dms(request: Request, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    channels = db.query(Channel).filter(Channel.workspace_id == workspace.id).all() if workspace else []
    users = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace.id,
        SlackUser.is_deleted == False,
        SlackUser.is_bot == False,
    ).all() if workspace else []
    # Deduplicated DM channels — at most one per other-user pair
    dm_channels = _dedup_dm_channels(db, channels, user.id) if user else []
    first_dm_id = dm_channels[0].id if dm_channels else None
    dm_names = _get_dm_names(db, channels, user.id) if user else {}
    # Build deduplicated sidebar channels list
    non_dm = [c for c in channels if not getattr(c, "is_im", False) and not getattr(c, "is_mpim", False)]
    sidebar_channels = non_dm + dm_channels
    return templates.TemplateResponse("dms.html", {
        "request": request, "workspace": workspace, "user": user,
        "channels": sidebar_channels, "users": users, "dm_channels": dm_channels,
        "dm_names": dm_names,
        "dm_users": _get_dm_users(db, sidebar_channels, user.id) if user else {},
        "first_dm_id": first_dm_id,
    })

@router.get("/activity", response_class=HTMLResponse)
async def view_activity(request: Request, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    channels = db.query(Channel).filter(Channel.workspace_id == workspace.id).all() if workspace else []
    channel_map = {ch.id: ch for ch in channels}
    user_map = {u.id: u for u in db.query(SlackUser).filter(SlackUser.workspace_id == workspace.id).all()} if workspace else {}

    activity_items = []

    if workspace and user:
        # ── Mentions: direct mentions of this user only ──────────────────
        from sqlalchemy import or_
        mention_msgs = db.query(Message).filter(
            or_(
                Message.text.like(f'%<@{user.id}>%'),
                Message.text.like(f'%@{user.name}%'),
            ),
            Message.workspace_id == workspace.id,
            Message.user_id != user.id,
        ).all()
        for m in mention_msgs:
            activity_items.append({
                "type": "mention",
                "ts": float(m.ts),
                "actor": user_map.get(m.user_id),
                "channel": channel_map.get(m.channel_id),
                "message": m,
                "context": None,
                "emoji": None,
            })

        # ── Threads: replies by others in threads alex participated in ────
        alex_replies = db.query(Message).filter(
            Message.user_id == user.id,
            Message.workspace_id == workspace.id,
            Message.ts != Message.thread_ts,
        ).all()
        participated_thread_ts = {m.thread_ts for m in alex_replies}

        # Also include threads where alex is the parent author
        alex_parents = db.query(Message).filter(
            Message.user_id == user.id,
            Message.workspace_id == workspace.id,
            Message.ts == Message.thread_ts,
            Message.reply_count > 0,
        ).all()
        for p in alex_parents:
            participated_thread_ts.add(p.ts)

        if participated_thread_ts:
            other_thread_replies = db.query(Message).filter(
                Message.thread_ts.in_(participated_thread_ts),
                Message.user_id != user.id,
                Message.ts != Message.thread_ts,
                Message.workspace_id == workspace.id,
            ).all()
            # Load parent messages for context
            parent_map = {}
            for pts in participated_thread_ts:
                pm = db.query(Message).filter(Message.ts == pts, Message.workspace_id == workspace.id).first()
                if pm:
                    parent_map[pts] = pm

            for m in other_thread_replies:
                activity_items.append({
                    "type": "thread",
                    "ts": float(m.ts),
                    "actor": user_map.get(m.user_id),
                    "channel": channel_map.get(m.channel_id),
                    "message": m,
                    "context": parent_map.get(m.thread_ts),
                    "emoji": None,
                })

        # ── Reactions: emojis added to alex's messages ───────────────────
        reaction_rows = db.query(Reaction, Message).join(
            Message, Reaction.message_id == Message.id
        ).filter(
            Message.user_id == user.id,
            Message.workspace_id == workspace.id,
            Reaction.user_id != user.id,
        ).all()
        for r, m in reaction_rows:
            activity_items.append({
                "type": "reaction",
                "ts": float(m.ts),  # use message ts as proxy (reaction has no ts)
                "actor": user_map.get(r.user_id),
                "channel": channel_map.get(m.channel_id),
                "message": m,
                "context": None,
                "emoji": r.emoji_name,
            })

    # Sort all by ts desc (most recent first)
    activity_items.sort(key=lambda x: x["ts"], reverse=True)
    mentions = [x for x in activity_items if x["type"] == "mention"]
    threads  = [x for x in activity_items if x["type"] == "thread"]
    reactions = [x for x in activity_items if x["type"] == "reaction"]

    first_item = next((x for x in activity_items if x.get("channel")), None)
    first_channel_id = first_item["channel"].id if first_item else None
    first_ts = str(first_item["ts"]) if first_item else None

    return templates.TemplateResponse("activity.html", {
        "request": request, "workspace": workspace, "user": user,
        "channels": channels, "current_channel": None,
        "activity_items": activity_items,
        "mentions": mentions,
        "threads": threads,
        "reactions": reactions,
        "dm_names": _get_dm_names(db, channels, user.id) if user else {},
        "dm_users": _get_dm_users(db, channels, user.id) if user else {},
        "first_channel_id": first_channel_id,
        "first_ts": first_ts,
    })

@router.get("/files", response_class=HTMLResponse)
async def view_files(request: Request, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    channels = db.query(Channel).filter(Channel.workspace_id == workspace.id).all() if workspace else []
    channel_map = {ch.id: ch for ch in channels}
    user_map = {u.id: u for u in db.query(SlackUser).filter(SlackUser.workspace_id == workspace.id).all()} if workspace else {}
    all_files = db.query(SlackFile).filter(SlackFile.workspace_id == workspace.id).order_by(SlackFile.created_at.desc()).all() if workspace else []
    my_files = [f for f in all_files if f.user_id == user.id] if user else []
    shared_files = [f for f in all_files if f.user_id != (user.id if user else None)] if user else all_files
    return templates.TemplateResponse("files.html", {
        "request": request, "workspace": workspace, "user": user,
        "channels": channels, "current_channel": None,
        "all_files": all_files, "my_files": my_files, "shared_files": shared_files,
        "channel_map": channel_map, "user_map": user_map,
        "dm_names": _get_dm_names(db, channels, user.id) if user else {},
        "dm_users": _get_dm_users(db, channels, user.id) if user else {},
    })

@router.post("/files/delete", response_class=JSONResponse)
async def delete_file(request: Request, file_id: str = Form(...), db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not user:
        return JSONResponse({"ok": False, "error": "not_authenticated"}, status_code=403)
    f = db.query(SlackFile).filter(SlackFile.id == file_id, SlackFile.workspace_id == workspace.id).first() if workspace else None
    if not f:
        return JSONResponse({"ok": False, "error": "file_not_found"}, status_code=404)
    if f.user_id != user.id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    db.delete(f)
    db.commit()
    return JSONResponse({"ok": True})

@router.get("/later", response_class=HTMLResponse)
async def view_later(request: Request, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    workspace, user = _get_current_workspace_and_user(db, request)
    channels = db.query(Channel).filter(Channel.workspace_id == workspace.id).all() if workspace else []
    now = datetime.utcnow()
    reminders = []
    if workspace and user:
        raw = db.query(Reminder).filter(
            Reminder.workspace_id == workspace.id,
            Reminder.user_id == user.id,
        ).order_by(Reminder.remind_at).all()
        for r in raw:
            overdue_days = (now - r.remind_at).days if r.remind_at and r.remind_at < now else 0
            reminders.append({
                "id": r.id,
                "text": r.text,
                "remind_at": r.remind_at,
                "is_complete": r.is_complete,
                "overdue_days": overdue_days,
                "is_overdue": overdue_days > 0 and not r.is_complete,
            })
    in_progress = [r for r in reminders if not r["is_complete"]]
    completed   = [r for r in reminders if r["is_complete"]]
    return templates.TemplateResponse("later.html", {
        "request": request, "workspace": workspace, "user": user,
        "channels": channels, "current_channel": None,
        "in_progress": in_progress, "completed": completed,
        "dm_names": _get_dm_names(db, channels, user.id) if user else {},
        "dm_users": _get_dm_users(db, channels, user.id) if user else {},
    })

@router.get("/more", response_class=HTMLResponse)
async def view_more(request: Request, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    channels = db.query(Channel).filter(Channel.workspace_id == workspace.id).all() if workspace else []
    return templates.TemplateResponse(request, "dashboard.html", context={
        "workspace": workspace, "user": user, "channels": channels,
        "message": "More menu coming soon.",
        "dm_names": _get_dm_names(db, channels, user.id) if user else {},
        "dm_users": _get_dm_users(db, channels, user.id) if user else {},
    })

@router.get("/search", response_class=HTMLResponse)
async def search_view(request: Request, q: str = Query(default=""), db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    channels = _get_workspace_channels(db, workspace.id, user.id) if workspace and user else []

    results = []
    if q:
        msgs = (
            db.query(Message)
            .filter(Message.workspace_id == workspace.id, Message.text.ilike(f"%{q}%"))
            .order_by(Message.ts.desc())
            .limit(50)
            .all()
        )
        ch_map = {c.id: c for c in db.query(Channel).filter(Channel.workspace_id == workspace.id).all()}
        for msg in msgs:
            ch = ch_map.get(msg.channel_id)
            results.append({"msg": msg, "channel": ch})

    return templates.TemplateResponse(request, "search.html", context={
        "workspace": workspace,
        "user": user,
        "channels": channels,
        "dm_names": _get_dm_names(db, channels, user.id) if user else {},
        "dm_users": _get_dm_users(db, channels, user.id) if user else {},
        "query": q,
        "results": results,
    })


@router.get("/tools", response_class=HTMLResponse)
async def view_tools(request: Request, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    channels = db.query(Channel).filter(Channel.workspace_id == workspace.id).all() if workspace else []
    return templates.TemplateResponse(request, "dashboard.html", context={
        "workspace": workspace, "user": user, "channels": channels,
        "message": "Tools & Apps menu coming soon.",
        "dm_names": _get_dm_names(db, channels, user.id) if user else {},
        "dm_users": _get_dm_users(db, channels, user.id) if user else {},
    })

@router.get("/channel/{channel_id}", response_class=HTMLResponse)
async def view_channel(request: Request, channel_id: str, new: str = Query(default=None), db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return HTMLResponse("Not found", status_code=404)

    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        return HTMLResponse("Channel not found", status_code=404)

    messages = db.query(Message).filter(
        Message.channel_id == channel_id,
        (Message.thread_ts == Message.ts) | Message.thread_ts.is_(None),
    ).order_by(Message.ts.asc()).all()
    # Eager load user? Just fetch them or use relationship

    channels = _get_workspace_channels(db, workspace.id, user.id)
    channel_member_count = db.query(ChannelMember).filter(ChannelMember.channel_id == channel_id).count()
    channel_members = (
        db.query(SlackUser)
        .join(ChannelMember, ChannelMember.user_id == SlackUser.id)
        .filter(ChannelMember.channel_id == channel_id)
        .order_by(SlackUser.real_name.asc(), SlackUser.name.asc())
        .all()
    )
    channel_creator = (
        db.query(SlackUser)
        .filter(SlackUser.id == channel.creator_id, SlackUser.workspace_id == workspace.id)
        .first()
    )

    # For new channels, get other members (non-creator) to show in join message
    new_channel_members = []
    if new == "1":
        members = (
            db.query(SlackUser)
            .join(ChannelMember, ChannelMember.user_id == SlackUser.id)
            .filter(ChannelMember.channel_id == channel_id, SlackUser.id != channel.creator_id)
            .all()
        )
        new_channel_members = [m.real_name or m.name for m in members]

    thread_preview_users, latest_reply_at = _build_thread_preview_maps(
        db,
        channel_id=channel_id,
        parent_messages=messages,
    )

    # For DM channels, resolve the other person's display name
    dm_display_name = None
    dm_other_user = None
    if channel.is_im:
        other_member = (
            db.query(SlackUser)
            .join(ChannelMember, ChannelMember.user_id == SlackUser.id)
            .filter(ChannelMember.channel_id == channel_id, SlackUser.id != user.id)
            .first()
        )
        if other_member:
            dm_display_name = other_member.real_name or other_member.name
            dm_other_user = other_member
    _normalize_message_attachment_footers(
        db,
        workspace_id=workspace.id,
        current_user_id=user.id,
        messages=messages,
    )

    return templates.TemplateResponse(request, "channel.html", context={
        "workspace": workspace,
        "user": user,
        "channels": channels,
        "current_channel": channel, "has_unread_threads": True,
        "messages": messages,
        "channel_member_count": channel_member_count,
        "channel_members": channel_members,
        "channel_creator_name": (
            channel_creator.real_name
            or channel_creator.name
            if channel_creator else "Unknown"
        ),
        "is_new_channel": new == "1",
        "new_channel_members": new_channel_members,
        "dm_display_name": dm_display_name,
        "dm_other_user": dm_other_user,
        "dm_names": _get_dm_names(db, channels, user.id),
        "dm_users": _get_dm_users(db, channels, user.id),
        "thread_preview_users": thread_preview_users,
        "latest_reply_at": latest_reply_at,
        "now": datetime.utcnow(),
    })

@router.get("/channel/{channel_id}/inline", response_class=HTMLResponse)
async def view_channel_inline(
    request: Request,
    channel_id: str,
    highlight: str = Query(default=None),
    db: Session = Depends(get_db)
):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return HTMLResponse("Not found", status_code=404)
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        return HTMLResponse("Channel not found", status_code=404)
    messages = db.query(Message).filter(
        Message.channel_id == channel_id,
        (Message.thread_ts == Message.ts) | Message.thread_ts.is_(None),
    ).order_by(Message.ts.asc()).all()
    dm_display_name = None
    dm_other_user = None
    if channel.is_im:
        other_member = (
            db.query(SlackUser)
            .join(ChannelMember, ChannelMember.user_id == SlackUser.id)
            .filter(ChannelMember.channel_id == channel_id, SlackUser.id != user.id)
            .first()
        )
        if other_member:
            dm_display_name = other_member.real_name or other_member.name
            dm_other_user = other_member
    _normalize_message_attachment_footers(
        db,
        workspace_id=workspace.id,
        current_user_id=user.id,
        messages=messages,
    )
    thread_preview_users, latest_reply_at = _build_thread_preview_maps(
        db,
        channel_id=channel_id,
        parent_messages=messages,
    )
    return templates.TemplateResponse("channel_inline.html", {
        "request": request, "workspace": workspace, "user": user,
        "channel": channel, "messages": messages,
        "dm_display_name": dm_display_name, "dm_other_user": dm_other_user,
        "highlight": highlight,
        "thread_preview_users": thread_preview_users,
        "latest_reply_at": latest_reply_at,
        "now": datetime.utcnow(),
    })

@router.post("/channel/{channel_id}/message/inline", response_class=HTMLResponse)
async def send_message_inline(
    request: Request,
    channel_id: str,
    text: str = Form(...),
    db: Session = Depends(get_db)
):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return HTMLResponse("Not authorized", status_code=403)
    _create_message(db, workspace_id=workspace.id, channel_id=channel_id, user_id=user.id, text=text)
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    messages = db.query(Message).filter(
        Message.channel_id == channel_id,
        (Message.thread_ts == Message.ts) | Message.thread_ts.is_(None),
    ).order_by(Message.ts.asc()).all()
    dm_display_name = None
    dm_other_user = None
    if channel and channel.is_im:
        other_member = (
            db.query(SlackUser)
            .join(ChannelMember, ChannelMember.user_id == SlackUser.id)
            .filter(ChannelMember.channel_id == channel_id, SlackUser.id != user.id)
            .first()
        )
        if other_member:
            dm_display_name = other_member.real_name or other_member.name
            dm_other_user = other_member
    _normalize_message_attachment_footers(
        db,
        workspace_id=workspace.id,
        current_user_id=user.id,
        messages=messages,
    )
    thread_preview_users, latest_reply_at = _build_thread_preview_maps(
        db,
        channel_id=channel_id,
        parent_messages=messages,
    )
    return templates.TemplateResponse("channel_inline.html", {
        "request": request, "workspace": workspace, "user": user,
        "channel": channel, "messages": messages,
        "dm_display_name": dm_display_name, "dm_other_user": dm_other_user,
        "highlight": None,
        "thread_preview_users": thread_preview_users,
        "latest_reply_at": latest_reply_at,
        "now": datetime.utcnow(),
    })

@router.post("/channel/{channel_id}/message", response_class=HTMLResponse)
async def send_message(
    request: Request,
    channel_id: str,
    text: str = Form(...),
    db: Session = Depends(get_db)
):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return HTMLResponse("Not authorized", status_code=403)

    _create_message(
        db,
        workspace_id=workspace.id,
        channel_id=channel_id,
        user_id=user.id,
        text=text,
    )
    return RedirectResponse(f"/channel/{channel_id}", status_code=303)

@router.post("/channel/{channel_id}/forward")
async def forward_message(request: Request, channel_id: str, db: Session = Depends(get_db)):
    """Create a forwarded message with Slack-style attachments."""
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return JSONResponse({"ok": False, "error": "not_authed"}, status_code=403)
    body = await request.json()
    text = body.get("text", "")
    attachments = body.get("attachments") or None
    msg = _create_message(
        db,
        workspace_id=workspace.id,
        channel_id=channel_id,
        user_id=user.id,
        text=text,
        attachments=attachments,
    )
    return JSONResponse({"ok": True, "channel": channel_id, "ts": msg.ts})


@router.post("/channel/{channel_id}/message/delete")
async def delete_message(request: Request, channel_id: str, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return JSONResponse({"ok": False, "error": "not_authed"}, status_code=403)
    body = await request.json()
    ts = body.get("ts")
    msg = db.query(Message).filter(Message.channel_id == channel_id, Message.ts == ts).first()
    if not msg:
        return JSONResponse({"ok": False, "error": "message_not_found"}, status_code=404)
    # Enforce that only the author of the message can delete it.
    if msg.user_id != user.id:
        return JSONResponse({"ok": False, "error": "not_allowed"}, status_code=403)
    db.delete(msg)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/channel/{channel_id}/message/edit")
async def edit_message(
    request: Request,
    channel_id: str,
    ts: str = Form(...),
    text: str = Form(...),
    db: Session = Depends(get_db),
):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return RedirectResponse(f"/channel/{channel_id}", status_code=303)
    msg = db.query(Message).filter(Message.channel_id == channel_id, Message.ts == ts).first()
    if not msg or msg.user_id != user.id:
        return RedirectResponse(f"/channel/{channel_id}", status_code=303)
    from datetime import datetime
    msg.text = text
    msg.is_edited = True
    msg.edited_ts = str(datetime.utcnow().timestamp())
    db.commit()
    return RedirectResponse(f"/channel/{channel_id}", status_code=303)


@router.post("/channel/{channel_id}/react")
async def react_message(request: Request, channel_id: str, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return JSONResponse({"ok": False, "error": "not_authed"}, status_code=403)
    body = await request.json()
    ts = body.get("ts")
    emoji_name = body.get("emoji_name")
    action = body.get("action", "add")
    msg = db.query(Message).filter(Message.channel_id == channel_id, Message.ts == ts).first()
    if not msg:
        return JSONResponse({"ok": False, "error": "message_not_found"}, status_code=404)
    if action == "add":
        exists = db.query(Reaction).filter(
            Reaction.message_id == msg.id,
            Reaction.user_id == user.id,
            Reaction.emoji_name == emoji_name,
        ).first()
        if not exists:
            import uuid
            db.add(Reaction(id=uuid.uuid4().hex, message_id=msg.id, user_id=user.id, emoji_name=emoji_name))
            db.commit()
    else:
        db.query(Reaction).filter(
            Reaction.message_id == msg.id,
            Reaction.user_id == user.id,
            Reaction.emoji_name == emoji_name,
        ).delete()
        db.commit()
    return JSONResponse({"ok": True})


@router.post("/channel/{channel_id}/pin")
async def pin_message(request: Request, channel_id: str, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return JSONResponse({"ok": False, "error": "not_authed"}, status_code=403)
    body = await request.json()
    ts = body.get("ts")
    msg = db.query(Message).filter(Message.channel_id == channel_id, Message.ts == ts).first()
    if not msg:
        return JSONResponse({"ok": False, "error": "message_not_found"}, status_code=404)
    exists = db.query(Pin).filter(Pin.channel_id == channel_id, Pin.message_id == msg.id).first()
    if not exists:
        import uuid
        from datetime import datetime
        db.add(Pin(id=uuid.uuid4().hex, channel_id=channel_id, message_id=msg.id, user_id=user.id, created_at=datetime.utcnow()))
        msg.is_pinned = True
        db.commit()
    return JSONResponse({"ok": True})


@router.get("/channel/{channel_id}/permalink")
async def get_permalink(request: Request, channel_id: str, ts: str = Query(...), db: Session = Depends(get_db)):
    base = str(request.base_url).rstrip("/")
    permalink = f"{base}/channel/{channel_id}?ts={ts}"
    return JSONResponse({"ok": True, "permalink": permalink})


@router.get("/channel/{channel_id}/thread/{thread_ts}", response_class=HTMLResponse)
async def view_thread(request: Request, channel_id: str, thread_ts: str, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return HTMLResponse("Not found", status_code=404)
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        return HTMLResponse("Channel not found", status_code=404)
    parent = db.query(Message).filter(Message.channel_id == channel_id, Message.ts == thread_ts).first()
    if not parent:
        return HTMLResponse("Thread not found", status_code=404)
    replies = (
        db.query(Message)
        .filter(
            Message.channel_id == channel_id,
            Message.thread_ts == thread_ts,
            Message.ts != thread_ts,  # exclude parent (seed data: parent has thread_ts == ts)
        )
        .order_by(Message.created_at.asc())
        .all()
    )
    channels = db.query(Channel).filter(Channel.workspace_id == workspace.id).all()
    dm_display_name = None
    dm_other_user = None
    if channel.is_im:
        other_member = (
            db.query(SlackUser)
            .join(ChannelMember, ChannelMember.user_id == SlackUser.id)
            .filter(ChannelMember.channel_id == channel_id, SlackUser.id != user.id)
            .first()
        )
        if other_member:
            dm_display_name = other_member.real_name or other_member.name
            dm_other_user = other_member
    _normalize_message_attachment_footers(
        db,
        workspace_id=workspace.id,
        current_user_id=user.id,
        messages=[parent, *replies],
    )
    return templates.TemplateResponse("thread.html", {
        "request": request,
        "workspace": workspace,
        "user": user,
        "channels": channels,
        "current_channel": channel,
        "parent": parent,
        "replies": replies,
        "dm_display_name": dm_display_name,
        "dm_other_user": dm_other_user,
        "dm_names": _get_dm_names(db, channels, user.id),
        "dm_users": _get_dm_users(db, channels, user.id),
    })


@router.get("/user/{user_id}/profile/panel", response_class=HTMLResponse)
async def user_profile_panel(request: Request, user_id: str, db: Session = Depends(get_db)):
    """Returns profile_panel.html partial for HTMX loading into #profile-panel."""
    workspace, current_user = _get_current_workspace_and_user(db, request)
    if not workspace or not current_user:
        return HTMLResponse("Not found", status_code=404)
    profile_user = db.query(SlackUser).filter(SlackUser.id == user_id).first()
    if not profile_user:
        return HTMLResponse("User not found", status_code=404)
    return templates.TemplateResponse("profile_panel.html", {
        "request": request,
        "workspace": workspace,
        "user": current_user,
        "profile_user": profile_user,
        "is_self": profile_user.id == current_user.id,
    })


@router.get("/channel/{channel_id}/thread/{thread_ts}/panel", response_class=HTMLResponse)
async def view_thread_panel(request: Request, channel_id: str, thread_ts: str, db: Session = Depends(get_db)):
    """Returns thread_panel.html partial (no base layout) for HTMX loading."""
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return HTMLResponse("Not found", status_code=404)
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        return HTMLResponse("Channel not found", status_code=404)
    parent = db.query(Message).filter(Message.channel_id == channel_id, Message.ts == thread_ts).first()
    if not parent:
        return HTMLResponse("Thread not found", status_code=404)
    replies = (
        db.query(Message)
        .filter(
            Message.channel_id == channel_id,
            Message.thread_ts == thread_ts,
            Message.ts != thread_ts,
        )
        .order_by(Message.created_at.asc())
        .all()
    )
    dm_display_name = None
    if channel.is_im:
        other_member = (
            db.query(SlackUser)
            .join(ChannelMember, ChannelMember.user_id == SlackUser.id)
            .filter(ChannelMember.channel_id == channel_id, SlackUser.id != user.id)
            .first()
        )
        if other_member:
            dm_display_name = other_member.real_name or other_member.name
    _normalize_message_attachment_footers(
        db,
        workspace_id=workspace.id,
        current_user_id=user.id,
        messages=[parent, *replies],
    )
    return templates.TemplateResponse("thread_panel.html", {
        "request": request,
        "workspace": workspace,
        "user": user,
        "current_channel": channel,
        "parent": parent,
        "replies": replies,
        "dm_display_name": dm_display_name,
    })


@router.post("/channel/{channel_id}/thread/{thread_ts}/reply", response_class=HTMLResponse)
async def post_thread_reply(
    request: Request,
    channel_id: str,
    thread_ts: str,
    text: str = Form(...),
    db: Session = Depends(get_db),
):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return RedirectResponse(f"/channel/{channel_id}/thread/{thread_ts}", status_code=303)
    _create_message(
        db,
        workspace_id=workspace.id,
        channel_id=channel_id,
        user_id=user.id,
        text=text,
        thread_ts=thread_ts,
    )
    return RedirectResponse(f"/channel/{channel_id}/thread/{thread_ts}", status_code=303)


@router.get("/drafts", response_class=HTMLResponse)
async def drafts(request: Request, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    channels = _get_workspace_channels(db, workspace.id, user.id) if workspace and user else []
    return templates.TemplateResponse(request, "drafts.html", context={
        "workspace": workspace, "user": user, "channels": channels,
        "has_unread_threads": True,
        "dm_names": _get_dm_names(db, channels, user.id) if user else {},
        "dm_users": _get_dm_users(db, channels, user.id) if user else {},
    })

@router.get("/directories", response_class=HTMLResponse)
async def directories(request: Request, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    channels = _get_workspace_channels(db, workspace.id, user.id) if workspace and user else []
    users = db.query(SlackUser).filter(SlackUser.workspace_id == workspace.id).all() if workspace else []
    return templates.TemplateResponse(request, "directories.html", context={
        "workspace": workspace, "user": user, "channels": channels, "users": users, "has_unread_threads": True,
        "message": "Directories (Channels & People).",
        "dm_names": _get_dm_names(db, channels, user.id) if user else {},
        "dm_users": _get_dm_users(db, channels, user.id) if user else {},
    })

@router.get("/app/{app_id}", response_class=HTMLResponse)
async def app_view(request: Request, app_id: str, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    channels = _get_workspace_channels(db, workspace.id, user.id) if workspace and user else []
    return templates.TemplateResponse(request, "dashboard.html", context={
        "workspace": workspace, "user": user, "channels": channels,
        "message": f"App View: {app_id.replace('-', ' ').title()}.",
        "dm_names": _get_dm_names(db, channels, user.id) if user else {},
        "dm_users": _get_dm_users(db, channels, user.id) if user else {},
    })

@router.get("/new", response_class=HTMLResponse)
async def new_message(
    request: Request,
    to: str | None = Query(default=None),
    text: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    workspace, user = _get_current_workspace_and_user(db, request)
    return templates.TemplateResponse(
        request,
        "new_message.html",
        context=_new_message_context(
            request,
            db,
            workspace=workspace,
            user=user,
            compose_target=to or "",
            compose_text=text or "",
        ),
    )


@router.get("/new/inline", response_class=HTMLResponse)
async def new_message_inline(
    request: Request,
    to: str | None = Query(default=None),
    text: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    workspace, user = _get_current_workspace_and_user(db, request)
    return _render_new_message_inline(
        request,
        db,
        workspace=workspace,
        user=user,
        compose_target=to or "",
        compose_text=text or "",
    )


@router.post("/new", response_class=HTMLResponse)
async def post_new_message(
    request: Request,
    target: str = Form(...),
    text: str = Form(...),
    db: Session = Depends(get_db),
):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return HTMLResponse("Not authorized", status_code=403)

    channel, error = _resolve_compose_target(
        db,
        workspace=workspace,
        current_user=user,
        target=target,
    )
    if error or not channel:
        return templates.TemplateResponse(
            request,
            "new_message.html",
            context=_new_message_context(
                request,
                db,
                workspace=workspace,
                user=user,
                compose_target=target,
                compose_text=text,
                compose_error=error,
            ),
            status_code=422,
        )

    _create_message(
        db,
        workspace_id=workspace.id,
        channel_id=channel.id,
        user_id=user.id,
        text=text,
    )
    return RedirectResponse(f"/channel/{channel.id}", status_code=303)


@router.post("/new/inline", response_class=HTMLResponse)
async def post_new_message_inline(
    request: Request,
    target: str = Form(...),
    text: str = Form(...),
    db: Session = Depends(get_db),
):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return HTMLResponse("Not authorized", status_code=403)

    channel, error = _resolve_compose_target(
        db,
        workspace=workspace,
        current_user=user,
        target=target,
    )
    if error or not channel:
        return _render_new_message_inline(
            request,
            db,
            workspace=workspace,
            user=user,
            compose_target=target,
            compose_text=text,
            compose_error=error,
        )

    _create_message(
        db,
        workspace_id=workspace.id,
        channel_id=channel.id,
        user_id=user.id,
        text=text,
    )

    messages = db.query(Message).filter(
        Message.channel_id == channel.id,
        (Message.thread_ts == Message.ts) | Message.thread_ts.is_(None),
    ).order_by(Message.ts.asc()).all()
    dm_display_name = None
    dm_other_user = None
    if channel.is_im:
        other_member = (
            db.query(SlackUser)
            .join(ChannelMember, ChannelMember.user_id == SlackUser.id)
            .filter(ChannelMember.channel_id == channel.id, SlackUser.id != user.id)
            .first()
        )
        if other_member:
            dm_display_name = other_member.real_name or other_member.name
            dm_other_user = other_member

    return templates.TemplateResponse("channel_inline.html", {
        "request": request,
        "workspace": workspace,
        "user": user,
        "channel": channel,
        "messages": messages,
        "dm_display_name": dm_display_name,
        "dm_other_user": dm_other_user,
        "highlight": None,
    })


@router.get("/new-dm/{user_id}")
async def open_new_dm(request: Request, user_id: str, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return HTMLResponse("Not authorized", status_code=403)

    target_user = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace.id,
        SlackUser.id == user_id,
        SlackUser.is_bot == False,
        SlackUser.is_deleted == False,
    ).first()
    if not target_user:
        return RedirectResponse("/dms", status_code=303)

    channel = _get_or_create_dm_channel(
        db,
        workspace_id=workspace.id,
        current_user=user,
        other_user=target_user,
    )
    return RedirectResponse(f"/channel/{channel.id}", status_code=303)

@router.get("/threads", response_class=HTMLResponse)
async def threads_view(request: Request, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    if not workspace or not user:
        return HTMLResponse("Not found", status_code=404)

    all_channels = db.query(Channel).filter(Channel.workspace_id == workspace.id).all()
    channel_map = {c.id: c.name for c in all_channels}
    channel_obj_map = {c.id: c for c in all_channels}
    channels = _get_workspace_channels(db, workspace.id, user.id)

    # Threads the current user participated in:
    # 1) Parent messages authored by user (thread_ts == ts, seed convention) with replies
    # 2) Threads where user posted a reply (ts != thread_ts)
    authored_ts = {
        m.ts for m in db.query(Message).filter(
            Message.workspace_id == workspace.id,
            Message.user_id == user.id,
            Message.thread_ts == Message.ts,  # seed convention: parent self-refs
            Message.reply_count > 0,
        ).all()
    }
    # Also catch parents with NULL thread_ts (web UI posted parents)
    authored_ts |= {
        m.ts for m in db.query(Message).filter(
            Message.workspace_id == workspace.id,
            Message.user_id == user.id,
            Message.thread_ts.is_(None),
            Message.reply_count > 0,
        ).all()
    }
    replied_ts = {
        m.thread_ts for m in db.query(Message).filter(
            Message.workspace_id == workspace.id,
            Message.user_id == user.id,
            Message.ts != Message.thread_ts,  # reply: ts differs from thread_ts
            Message.thread_ts.isnot(None),
        ).all()
    }
    all_parent_ts = authored_ts | replied_ts

    parents = []
    for ts in all_parent_ts:
        p = db.query(Message).filter(
            Message.workspace_id == workspace.id,
            Message.ts == ts,
        ).first()
        if p:
            parents.append(p)

    thread_items = []
    for parent in parents:
        replies = (
            db.query(Message)
            .filter(
                Message.channel_id == parent.channel_id,
                Message.thread_ts == parent.ts,
                Message.ts != parent.ts,  # exclude the parent itself
            )
            .order_by(Message.created_at.desc())
            .all()
        )
        latest_reply = replies[0] if replies else None
        latest_ts = latest_reply.ts if latest_reply else parent.ts
        ch = channel_obj_map.get(parent.channel_id)
        dm_display_name = None
        if ch and ch.is_im:
            other = (
                db.query(SlackUser)
                .join(ChannelMember, ChannelMember.user_id == SlackUser.id)
                .filter(ChannelMember.channel_id == ch.id, SlackUser.id != user.id)
                .first()
            )
            if other:
                dm_display_name = other.real_name or other.name
        thread_items.append({
            "parent": parent,
            "replies": list(reversed(replies)),  # chronological for display
            "latest_reply": latest_reply,
            "reply_count": len(replies),
            "latest_ts": latest_ts,
            "channel_name": channel_map.get(parent.channel_id, "unknown"),
            "dm_display_name": dm_display_name,
        })

    # Sort by most recently active first
    thread_items.sort(key=lambda t: float(t["latest_ts"]), reverse=True)

    return templates.TemplateResponse("threads.html", {
        "request": request,
        "workspace": workspace,
        "user": user,
        "channels": channels,
        "threads": thread_items,
        "dm_names": _get_dm_names(db, channels, user.id) if user else {},
        "dm_users": _get_dm_users(db, channels, user.id) if user else {},
    })


# ─── Dev Tools ────────────────────────────────────────────────────────────────

def _build_dev_context(request: Request, db: Session, test_results=None) -> dict:
    workspace, user = _get_current_workspace_and_user(db, request)
    channels = db.query(Channel).filter(Channel.workspace_id == workspace.id).all() if workspace else []
    db_stats = {"messages": 0, "channels": 0, "users": 0, "files": 0}
    if workspace:
        db_stats = _get_dev_db_stats(db, workspace.id)
    test_inventory = _get_test_inventory()
    return {
        "request": request,
        "workspace": workspace,
        "user": user,
        "channels": channels,
        "current_channel": None,
        "has_unread_threads": False,
        "dm_names": _get_dm_names(db, channels, user.id) if user else {},
        "dm_users": _get_dm_users(db, channels, user.id) if user else {},
        "db_stats": db_stats,
        "test_results": test_results,
        "test_inventory": test_inventory,
    }


@router.get("/dev/dashboard", response_class=HTMLResponse)
async def dev_dashboard(request: Request, db: Session = Depends(get_db)):
    ctx = _build_dev_context(request, db)
    return templates.TemplateResponse(request, "dev_dashboard.html", context=ctx)


@router.post("/dev/dashboard/run-tests", response_class=HTMLResponse)
async def dev_run_tests(request: Request, db: Session = Depends(get_db)):
    report = _run_pytest()
    test_results = _parse_test_results(report) if report else None
    ctx = _build_dev_context(request, db, test_results=test_results)
    return templates.TemplateResponse(request, "dev_dashboard.html", context=ctx)


@router.get("/dev/api-explorer", response_class=HTMLResponse)
async def dev_api_explorer(request: Request, db: Session = Depends(get_db)):
    workspace, user = _get_current_workspace_and_user(db, request)
    channels = db.query(Channel).filter(Channel.workspace_id == workspace.id).all() if workspace else []
    sample_channel = db.query(Channel).filter(Channel.workspace_id == workspace.id).first() if workspace else None
    sample_user = db.query(SlackUser).filter(SlackUser.workspace_id == workspace.id, SlackUser.is_bot == False).first() if workspace else None
    sample_msg = db.query(Message).filter(Message.workspace_id == workspace.id).first() if workspace else None
    sample_file = db.query(SlackFile).filter(SlackFile.workspace_id == workspace.id).first() if workspace else None
    return templates.TemplateResponse(request, "api_explorer.html", context={
        "workspace": workspace,
        "user": user,
        "channels": channels,
        "current_channel": None,
        "has_unread_threads": False,
        "dm_names": _get_dm_names(db, channels, user.id) if user else {},
        "dm_users": _get_dm_users(db, channels, user.id) if user else {},
        "sample_channel_id": sample_channel.id if sample_channel else "C0000001",
        "sample_user_id": sample_user.id if sample_user else "U0000001",
        "sample_msg_ts": sample_msg.ts if sample_msg else "1700000000.000001",
        "sample_file_id": sample_file.id if sample_file else "F0000001",
    })


@router.get("/dev/db-viewer", response_class=HTMLResponse)
async def dev_db_viewer(
    request: Request,
    table: str = Query("messages", alias="table"),
    page: int = Query(1, alias="page"),
    db: Session = Depends(get_db),
):
    workspace, user = _get_current_workspace_and_user(db, request)
    channels = db.query(Channel).filter(Channel.workspace_id == workspace.id).all() if workspace else []

    per_page = 25
    offset = (page - 1) * per_page
    rows: list[dict] = []
    columns: list[str] = []
    total = 0

    ws_id = workspace.id if workspace else ""

    if table == "messages":
        columns = ["id", "channel_id", "user_id", "text", "ts", "thread_ts", "reply_count", "is_pinned", "created_at"]
        total = db.query(Message).filter(Message.workspace_id == ws_id).count()
        items = db.query(Message).filter(Message.workspace_id == ws_id).order_by(Message.created_at.desc()).offset(offset).limit(per_page).all()
        for m in items:
            rows.append({
                "id": m.id, "channel_id": m.channel_id, "user_id": m.user_id,
                "text": (m.text or "")[:80] + ("..." if len(m.text or "") > 80 else ""),
                "ts": m.ts, "thread_ts": m.thread_ts or "",
                "reply_count": m.reply_count or 0, "is_pinned": m.is_pinned,
                "created_at": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else "",
            })
    elif table == "channels":
        columns = ["id", "name", "is_private", "is_archived", "is_im", "topic", "purpose", "created_at"]
        total = db.query(Channel).filter(Channel.workspace_id == ws_id).count()
        items = db.query(Channel).filter(Channel.workspace_id == ws_id).offset(offset).limit(per_page).all()
        for c in items:
            rows.append({
                "id": c.id, "name": c.name, "is_private": c.is_private,
                "is_archived": c.is_archived, "is_im": c.is_im,
                "topic": (c.topic or "")[:60], "purpose": (c.purpose or "")[:60],
                "created_at": c.created_at.strftime("%Y-%m-%d") if c.created_at else "",
            })
    elif table == "users":
        columns = ["id", "name", "real_name", "email", "title", "presence", "is_admin", "is_bot"]
        total = db.query(SlackUser).filter(SlackUser.workspace_id == ws_id).count()
        items = db.query(SlackUser).filter(SlackUser.workspace_id == ws_id).offset(offset).limit(per_page).all()
        for u in items:
            rows.append({
                "id": u.id, "name": u.name, "real_name": u.real_name or "",
                "email": u.email or "", "title": u.title or "",
                "presence": u.presence or "active",
                "is_admin": u.is_admin, "is_bot": u.is_bot,
            })
    elif table == "reactions":
        columns = ["id", "message_id", "user_id", "emoji_name"]
        total = db.query(Reaction).join(Message).filter(Message.workspace_id == ws_id).count()
        items = db.query(Reaction).join(Message).filter(Message.workspace_id == ws_id).offset(offset).limit(per_page).all()
        for r in items:
            rows.append({"id": r.id, "message_id": r.message_id, "user_id": r.user_id, "emoji_name": r.emoji_name})
    elif table == "files":
        columns = ["id", "name", "title", "mimetype", "size", "is_public", "channel_id", "created_at"]
        total = db.query(SlackFile).filter(SlackFile.workspace_id == ws_id).count()
        items = db.query(SlackFile).filter(SlackFile.workspace_id == ws_id).offset(offset).limit(per_page).all()
        for f in items:
            rows.append({
                "id": f.id, "name": f.name or "", "title": f.title or "",
                "mimetype": f.mimetype or "", "size": f.size or 0,
                "is_public": f.is_public, "channel_id": f.channel_id or "",
                "created_at": f.created_at.strftime("%Y-%m-%d") if f.created_at else "",
            })
    elif table == "pins":
        columns = ["id", "channel_id", "message_id", "user_id", "created_at"]
        total = db.query(Pin).filter(Pin.channel_id.in_(
            db.query(Channel.id).filter(Channel.workspace_id == ws_id)
        )).count()
        items = db.query(Pin).filter(Pin.channel_id.in_(
            db.query(Channel.id).filter(Channel.workspace_id == ws_id)
        )).offset(offset).limit(per_page).all()
        for p in items:
            rows.append({
                "id": p.id, "channel_id": p.channel_id,
                "message_id": p.message_id or "", "user_id": p.user_id or "",
                "created_at": p.created_at.strftime("%Y-%m-%d") if p.created_at else "",
            })
    elif table == "reminders":
        columns = ["id", "creator_id", "user_id", "text", "remind_at", "is_complete"]
        total = db.query(Reminder).filter(Reminder.workspace_id == ws_id).count()
        items = db.query(Reminder).filter(Reminder.workspace_id == ws_id).offset(offset).limit(per_page).all()
        for r in items:
            rows.append({
                "id": r.id, "creator_id": r.creator_id, "user_id": r.user_id,
                "text": (r.text or "")[:80], "remind_at": str(r.remind_at or ""),
                "is_complete": r.is_complete,
            })

    total_pages = max(1, (total + per_page - 1) // per_page)
    return templates.TemplateResponse(request, "db_viewer.html", context={
        "workspace": workspace,
        "user": user,
        "channels": channels,
        "current_channel": None,
        "has_unread_threads": False,
        "table": table,
        "columns": columns,
        "rows": rows,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "tables": ["messages", "channels", "users", "reactions", "files", "pins", "reminders"],
    })

