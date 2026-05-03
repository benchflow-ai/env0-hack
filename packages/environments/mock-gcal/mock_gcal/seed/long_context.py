"""Long-context seeding helpers for Calendar scenarios.

This module mirrors the Gmail seed architecture: fixed "needle" events first,
then deterministic distribution-based filling from reusable template pools.
"""

from __future__ import annotations

import json
import zoneinfo
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy.orm import Session

from mock_gcal.models import Calendar, Event, User
from mock_gcal.seed.content import (
    CITY_NAMES,
    DEFAULT_DISTRIBUTION,
    DEFAULT_TARGET_EVENTS,
    EVENT_POOLS,
    LONG_CONTEXT_DISTRIBUTION,
    LONG_CONTEXT_TARGET_EVENTS,
    MEETING_TOPICS,
    NEEDLE_EVENTS,
    PERSONAS,
    PROJECT_NAMES,
    RECURRING_NEEDLES,
    ROOM_NAMES,
)


def _hour_to_parts(hour_value: float) -> tuple[int, int]:
    hour = int(hour_value)
    minute = int(round((hour_value - hour) * 60))
    if minute >= 60:
        hour += 1
        minute = 0
    return hour % 24, minute


def _safe_format(text: str, replacements: dict[str, str]) -> str:
    try:
        return text.format(**replacements)
    except KeyError:
        return text


def _parse_iso_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _next_weekday_delta(anchor_day: date, target_weekday: int) -> int:
    """Return days until the next weekday, preserving existing task semantics."""
    today = anchor_day.weekday()
    delta = (target_weekday - today) % 7
    return delta if delta > 0 else 7


def _resolve_temporal_fields(
    template: dict,
    rng,
    *,
    anchor_now: datetime,
) -> tuple[int, float, float, bool, int, bool]:
    """Resolve time-related fields into a normalized seed tuple.

    Returns (days_from_now, start_hour_value, duration_hours, all_day,
    duration_days, is_utc).

    WARNING: is_utc matters for timezone conversion downstream.
    start_iso hours are already UTC - they must NOT be re-interpreted
    as local time. Relative hours (weekday/days_from_now/start_date)
    are local time and need local-to-UTC conversion.
    """
    if template.get("start_iso"):
        start_dt = _parse_iso_datetime(str(template["start_iso"]))
        end_iso = template.get("end_iso")
        if end_iso:
            end_dt = _parse_iso_datetime(str(end_iso))
        else:
            end_dt = start_dt + timedelta(hours=float(template.get("duration_hours", 1)))

        duration_hours = max((end_dt - start_dt).total_seconds() / 3600, 0.25)
        # is_utc=True: hours extracted from UTC ISO string, skip local tz conversion
        return (
            (start_dt.date() - anchor_now.date()).days,
            start_dt.hour + (start_dt.minute / 60),
            duration_hours,
            False,
            1,
            True,
        )

    if template.get("start_date"):
        start_day = date.fromisoformat(str(template["start_date"]))
        all_day = bool(template.get("all_day", False))
        duration_days = int(template.get("duration_days", 1))
        if template.get("end_date"):
            end_day = date.fromisoformat(str(template["end_date"]))
            duration_days = max((end_day - start_day).days, 1)

        if all_day:
            return (
                (start_day - anchor_now.date()).days,
                0.0,
                24.0,
                True,
                duration_days,
                False,
            )

        if "start_hour" in template:
            start_hour_value = float(template["start_hour"])
        else:
            start_hour_value = float(rng.choice(template.get("start_hour_choices", [9, 10, 14])))

        if "duration_hours" in template:
            duration_hours = float(template["duration_hours"])
        else:
            duration_hours = float(rng.choice(template.get("duration_hours_choices", [1, 2])))

        return (
            (start_day - anchor_now.date()).days,
            start_hour_value,
            duration_hours,
            False,
            duration_days,
            False,
        )

    if template.get("weekday") is not None:
        weekday = int(template["weekday"])
        week_offset = int(template.get("week_offset", 0))
        days_from_now = _next_weekday_delta(anchor_now.date(), weekday) + (week_offset * 7)
    elif "days_from_now" in template:
        days_from_now = int(template["days_from_now"])
    else:
        lo, hi = template.get("days_from_now_range", (-30, 30))
        days_from_now = rng.randint(int(lo), int(hi))

    all_day = bool(template.get("all_day", False))
    duration_days = int(template.get("duration_days", 1))

    if "start_hour" in template:
        start_hour_value = float(template["start_hour"])
    else:
        start_hour_value = float(rng.choice(template.get("start_hour_choices", [9, 10, 14])))

    if "duration_hours" in template:
        duration_hours = float(template["duration_hours"])
    else:
        duration_hours = float(rng.choice(template.get("duration_hours_choices", [1, 2])))

    return days_from_now, start_hour_value, duration_hours, all_day, duration_days, False


def _materialize_attendee_keys(template: dict, rng) -> list[str]:
    explicit = template.get("attendees")
    if isinstance(explicit, list):
        return [str(a) for a in explicit]

    pool = template.get("attendees_pool")
    if not isinstance(pool, list) or not pool:
        return []

    lo, hi = template.get("attendees_count_range", (1, len(pool)))
    lo = max(0, int(lo))
    hi = min(len(pool), int(hi))
    if hi < lo:
        lo, hi = hi, lo
    count = rng.randint(lo, hi) if hi > 0 else 0
    if count <= 0:
        return []
    return rng.sample([str(p) for p in pool], k=count)


def _email_to_display_name(email: str) -> str:
    return email.split("@", 1)[0].replace(".", " ").replace("_", " ").title()


def _attendee_from_key(
    key: str,
    *,
    response_status: str = "needsAction",
    is_self: bool = False,
    user: User | None = None,
) -> dict[str, Any] | None:
    normalized_key = str(key).strip()
    if not normalized_key:
        return None

    if normalized_key == "self" and user is not None:
        attendee: dict[str, Any] = {
            "email": user.email_address,
            "displayName": user.display_name,
            "responseStatus": response_status,
            "self": True,
        }
        return attendee

    persona = PERSONAS.get(normalized_key)
    if persona:
        attendee = {
            "email": persona["email"],
            "displayName": persona["name"],
            "responseStatus": response_status,
        }
        if is_self:
            attendee["self"] = True
        return attendee

    if "@" in normalized_key:
        attendee = {
            "email": normalized_key,
            "displayName": _email_to_display_name(normalized_key),
            "responseStatus": response_status,
        }
        if is_self:
            attendee["self"] = True
        return attendee

    return None


def _materialize_explicit_attendee(
    raw_attendee: object,
    *,
    replacements: Mapping[str, str],
    user: User,
) -> dict[str, Any] | None:
    if isinstance(raw_attendee, str):
        return _attendee_from_key(raw_attendee, user=user)
    if not isinstance(raw_attendee, Mapping):
        return None

    response_status = str(raw_attendee.get("responseStatus", "needsAction"))
    persona_key = str(raw_attendee.get("persona") or raw_attendee.get("key") or "").strip()
    wants_self = bool(raw_attendee.get("self")) or persona_key == "self"
    if persona_key:
        attendee = _attendee_from_key(
            persona_key,
            response_status=response_status,
            is_self=wants_self,
            user=user,
        )
        if attendee is not None:
            return attendee

    email = _safe_format(str(raw_attendee.get("email") or ""), dict(replacements)).strip()
    if not email and wants_self:
        email = user.email_address
    if not email:
        return None

    display_name = _safe_format(
        str(raw_attendee.get("displayName") or raw_attendee.get("name") or ""),
        dict(replacements),
    ).strip()
    if not display_name:
        display_name = user.display_name if wants_self else _email_to_display_name(email)

    attendee = {
        "email": email,
        "displayName": display_name,
        "responseStatus": response_status,
    }
    if wants_self or email.lower() == user.email_address.lower():
        attendee["self"] = True
    return attendee


def _attendees_json(
    attendee_keys: list[str],
    *,
    explicit_attendees: list[object] | None = None,
    replacements: Mapping[str, str] | None = None,
    user: User,
) -> str:
    attendees_by_email: dict[str, dict[str, Any]] = {}

    for key in attendee_keys:
        attendee = _attendee_from_key(key, user=user)
        if attendee is None:
            continue
        attendees_by_email[str(attendee["email"]).strip().lower()] = attendee

    for raw_attendee in explicit_attendees or []:
        attendee = _materialize_explicit_attendee(
            raw_attendee,
            replacements=replacements or {},
            user=user,
        )
        if attendee is None:
            continue
        attendees_by_email[str(attendee["email"]).strip().lower()] = attendee

    return json.dumps(list(attendees_by_email.values()), separators=(",", ":"))


def _materialize_template(
    template: dict,
    rng,
    *,
    user: User,
    anchor_now: datetime | None = None,
) -> dict:
    anchor = (anchor_now or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    replacements = {
        "project": rng.choice(PROJECT_NAMES),
        "topic": rng.choice(MEETING_TOPICS),
        "city": rng.choice(CITY_NAMES),
        "room": rng.choice(ROOM_NAMES),
        "persona": rng.choice([p["name"] for p in PERSONAS.values()]),
        "user_email": user.email_address,
        "user_name": user.display_name,
    }

    summary = _safe_format(str(template.get("summary", "")), replacements)
    description = _safe_format(str(template.get("description", "")), replacements)
    location = _safe_format(str(template.get("location", "")), replacements)

    days_from_now, start_hour_value, duration_hours, all_day, duration_days, is_utc = _resolve_temporal_fields(
        template,
        rng,
        anchor_now=anchor,
    )
    start_hour, start_minute = _hour_to_parts(start_hour_value)

    if (
        "start_hour" not in template
        and "start_iso" not in template
        and not all_day
    ):
        minute_choices = template.get("start_minute_choices", [0, 15, 30, 45])
        start_minute = int(rng.choice(minute_choices))

    status = str(template.get("status", "confirmed"))
    cancelled_ratio = float(template.get("cancelled_ratio", 0.0))
    if "status" not in template and cancelled_ratio > 0 and rng.random() < cancelled_ratio:
        status = "cancelled"

    recurrence = template.get("recurrence", [])
    if not isinstance(recurrence, list):
        recurrence = []

    return {
        "summary": summary,
        "description": description,
        "location": location,
        "calendar": str(template.get("calendar", "primary")),
        "days_from_now": days_from_now,
        "all_day": all_day,
        "duration_days": duration_days,
        "start_hour": start_hour,
        "start_minute": start_minute,
        "duration_hours": duration_hours,
        "is_utc": is_utc,
        "status": status,
        "recurrence": recurrence,
        "attendees_json": _attendees_json(
            _materialize_attendee_keys(template, rng),
            explicit_attendees=template.get("attendees_data"),
            replacements=replacements,
            user=user,
        ),
    }


def _event_start_end(
    materialized: dict,
    anchor_now: datetime,
    local_tz: zoneinfo.ZoneInfo | None = None,
) -> tuple[datetime, datetime]:
    """Convert materialized event fields to UTC start/end datetimes.

    WARNING: start_hour/start_minute timezone depends on the source:
      - start_iso events (is_utc=True):  hours are already UTC, do NOT apply local_tz
      - relative events  (is_utc=False): hours are local time, convert via local_tz
    Mixing these up shifts events by the UTC offset (7-8h for US/Pacific).
    """
    event_day = (anchor_now + timedelta(days=materialized["days_from_now"])).date()
    if materialized["all_day"]:
        start_dt = datetime.combine(event_day, time.min, tzinfo=timezone.utc)
        end_dt = start_dt + timedelta(days=max(1, materialized["duration_days"]))
        return start_dt, end_dt

    # start_iso hours are already UTC; only apply local_tz for relative events
    tz = timezone.utc if materialized.get("is_utc") else (local_tz or timezone.utc)
    start_dt = datetime.combine(
        event_day,
        time(materialized["start_hour"], materialized["start_minute"], tzinfo=tz),
    ).astimezone(timezone.utc)
    end_dt = start_dt + timedelta(hours=max(0.25, materialized["duration_hours"]))
    return start_dt, end_dt


def _insert_event(
    db: Session,
    *,
    user: User,
    calendars_by_key: Mapping[str, Calendar],
    materialized: dict,
    event_index: int,
    anchor_now: datetime,
) -> str:
    calendar = calendars_by_key.get(materialized["calendar"]) or calendars_by_key.get("primary")
    if calendar is None:
        raise ValueError("Missing primary calendar for event insertion")

    try:
        local_tz = zoneinfo.ZoneInfo(user.timezone)
    except Exception:
        local_tz = None
    start_dt, end_dt = _event_start_end(materialized, anchor_now, local_tz=local_tz)
    event_id = f"evt_{user.id}_{event_index:05d}"
    created_at = anchor_now - timedelta(days=180) + timedelta(minutes=event_index)

    event = Event(
        id=event_id,
        calendar_id=calendar.id,
        user_id=user.id,
        summary=materialized["summary"],
        description=materialized["description"],
        location=materialized["location"],
        status=materialized["status"],
        start_dt=start_dt,
        end_dt=end_dt,
        start_is_date=bool(materialized["all_day"]),
        end_is_date=bool(materialized["all_day"]),
        attendees_json=materialized["attendees_json"],
        created_at=created_at,
        updated_at=created_at,
        etag=f'"{event_id}-v1"',
        i_cal_uid=f"{event_id}@smolclaw.local",
        sequence=0,
        recurrence_json=json.dumps(materialized["recurrence"], separators=(",", ":")),
        recurring_event_id="",
        original_start_time="",
    )
    db.add(event)
    return event_id


def _fill_from_pool(
    db: Session,
    *,
    user: User,
    calendars_by_key: Mapping[str, Calendar],
    pool: list[dict],
    count: int,
    start_index: int,
    anchor_now: datetime,
    rng,
) -> int:
    inserted = 0
    for i in range(count):
        template = pool[i % len(pool)]
        materialized = _materialize_template(template, rng, user=user, anchor_now=anchor_now)
        _insert_event(
            db,
            user=user,
            calendars_by_key=calendars_by_key,
            materialized=materialized,
            event_index=start_index + inserted,
            anchor_now=anchor_now,
        )
        inserted += 1
    return inserted


def _normalize_distribution(
    distribution: Mapping[str, float] | None,
) -> dict[str, float]:
    source = distribution or DEFAULT_DISTRIBUTION
    normalized: dict[str, float] = {}
    for key, value in source.items():
        if key not in EVENT_POOLS:
            continue
        weight = float(value)
        if weight > 0:
            normalized[key] = weight

    if normalized:
        return normalized
    return {key: 1.0 for key in EVENT_POOLS}


def _split_counts(total: int, distribution: Mapping[str, float]) -> dict[str, int]:
    if total <= 0:
        return {k: 0 for k in distribution}

    weight_sum = sum(distribution.values())
    raw_counts = {
        key: (total * (weight / weight_sum)) if weight_sum > 0 else 0.0
        for key, weight in distribution.items()
    }
    counts = {key: int(value) for key, value in raw_counts.items()}

    remainder = total - sum(counts.values())
    if remainder > 0:
        order = sorted(
            distribution.keys(),
            key=lambda key: raw_counts[key] - counts[key],
            reverse=True,
        )
        for idx in range(remainder):
            counts[order[idx % len(order)]] += 1

    return counts


def seed_distribution_scenario(
    db: Session,
    user: User,
    calendars_by_key: Mapping[str, Calendar],
    rng,
    *,
    target_events: int = DEFAULT_TARGET_EVENTS,
    distribution: Mapping[str, float] | None = None,
    needle_events: list[dict] | None = None,
    recurring_needles: list[dict] | None = None,
    include_needles: bool = True,
    anchor_now: datetime | None = None,
) -> int:
    """Seed one user with deterministic fixed needles + distribution fill."""
    anchor = (anchor_now or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    inserted = 0

    fixed_needles = needle_events if needle_events is not None else NEEDLE_EVENTS
    recurring = recurring_needles if recurring_needles is not None else RECURRING_NEEDLES

    if include_needles:
        for template in fixed_needles:
            materialized = _materialize_template(template, rng, user=user, anchor_now=anchor)
            _insert_event(
                db,
                user=user,
                calendars_by_key=calendars_by_key,
                materialized=materialized,
                event_index=inserted + 1,
                anchor_now=anchor,
            )
            inserted += 1

        for template in recurring:
            materialized = _materialize_template(template, rng, user=user, anchor_now=anchor)
            _insert_event(
                db,
                user=user,
                calendars_by_key=calendars_by_key,
                materialized=materialized,
                event_index=inserted + 1,
                anchor_now=anchor,
            )
            inserted += 1

    remaining = max(int(target_events) - inserted, 0)
    normalized_distribution = _normalize_distribution(distribution)
    counts = _split_counts(remaining, normalized_distribution)

    # Keep insertion order stable across runs by following EVENT_POOLS order.
    for pool_key in EVENT_POOLS:
        count = counts.get(pool_key, 0)
        if count <= 0:
            continue
        inserted += _fill_from_pool(
            db,
            user=user,
            calendars_by_key=calendars_by_key,
            pool=EVENT_POOLS[pool_key],
            count=count,
            start_index=inserted + 1,
            anchor_now=anchor,
            rng=rng,
        )

    return inserted


def seed_long_context_scenario(
    db: Session,
    user: User,
    calendars_by_key: Mapping[str, Calendar],
    rng,
    *,
    target_events: int = LONG_CONTEXT_TARGET_EVENTS,
    distribution: Mapping[str, float] | None = None,
    needle_events: list[dict] | None = None,
    recurring_needles: list[dict] | None = None,
    include_needles: bool = True,
) -> int:
    """Seed a high-volume scenario following long-context defaults."""
    return seed_distribution_scenario(
        db,
        user,
        calendars_by_key,
        rng,
        target_events=target_events,
        distribution=distribution or LONG_CONTEXT_DISTRIBUTION,
        needle_events=needle_events,
        recurring_needles=recurring_needles,
        include_needles=include_needles,
    )
