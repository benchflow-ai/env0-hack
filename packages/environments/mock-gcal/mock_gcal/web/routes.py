"""Web UI routes — Google Calendar-like interface using Jinja2 + HTMX."""

from __future__ import annotations

import ast
import calendar as _cal_mod
import json
import subprocess
import zoneinfo
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from mock_gcal.color_palette import (
    ALLOWED_CALENDAR_COLOR_IDS,
    DEFAULT_CALENDAR_COLOR_ID,
    calendar_background,
    canonical_calendar_color_id,
)
from mock_gcal.models import AclRule, Calendar, Event, User
from mock_gcal.state.action_log import action_log
from mock_gcal.state.snapshots import take_snapshot, restore_snapshot, list_snapshot_names
from mock_gcal.api.deps import get_db

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_DAY_ABBR = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_UI_HOUR_PX = 48
_TZ_CITY_LABELS = {
    "America/Los_Angeles": "Pacific Time - Los Angeles",
}


def _cal_color(color_id: str) -> str:
    return calendar_background(color_id)


def _cal_text_color(color_value: str) -> str:
    raw = color_value.lstrip("#")
    if len(raw) != 6:
        return "#ffffff"

    red = int(raw[0:2], 16)
    green = int(raw[2:4], 16)
    blue = int(raw[4:6], 16)
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    return "#1f1f1f" if luminance >= 0.68 else "#ffffff"


def _viewer_response(attendees: list[dict], viewer_email: str | None = None) -> str | None:
    viewer = (viewer_email or "").strip().lower()
    for attendee in attendees:
        response = str(attendee.get("responseStatus") or "").strip()
        if not response:
            continue
        if attendee.get("self") is True:
            return response
        email = str(attendee.get("email") or "").strip().lower()
        if viewer and email == viewer:
            return response
    return None


def _event_visual_state(status: str | None, viewer_response: str | None) -> str:
    normalized_status = str(status or "confirmed").strip().lower()
    normalized_response = str(viewer_response or "").strip().lower()
    if normalized_status == "cancelled":
        return "cancelled"
    if normalized_response == "needsaction":
        return "needs-action"
    if normalized_response in {"tentative", "declined"}:
        return normalized_response
    if normalized_status == "tentative":
        return "tentative"
    return "confirmed"


def _format_gmt_offset_label(offset: timedelta | None, *, with_minutes: bool = False) -> str:
    total_minutes = int((offset or timedelta()).total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    abs_minutes = abs(total_minutes)
    hours, minutes = divmod(abs_minutes, 60)
    if with_minutes:
        return f"GMT{sign}{hours:02d}:{minutes:02d}"
    if minutes:
        return f"GMT{sign}{hours:02d}:{minutes:02d}"
    return f"GMT{sign}{hours:02d}"


def _format_compact_time_range(start_dt: datetime, end_dt: datetime) -> str:
    start_fmt = "%-I" if start_dt.minute == 0 else "%-I:%M"
    end_fmt = "%-I" if end_dt.minute == 0 else "%-I:%M"
    start_text = start_dt.strftime(start_fmt)
    end_text = end_dt.strftime(end_fmt)
    start_meridiem = start_dt.strftime("%p").lower()
    end_meridiem = end_dt.strftime("%p").lower()
    if start_meridiem == end_meridiem:
        return f"{start_text} – {end_text}{end_meridiem}"
    return f"{start_text}{start_meridiem} – {end_text}{end_meridiem}"


def _friendly_timezone_label(tz_name: str) -> str:
    if tz_name in _TZ_CITY_LABELS:
        return _TZ_CITY_LABELS[tz_name]

    parts = [piece.replace("_", " ") for piece in tz_name.split("/") if piece]
    if not parts:
        return tz_name
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0].replace('_', ' ')} Time - {parts[-1]}"


def _partition_sidebar_calendars(calendars: list[Calendar]) -> tuple[list[Calendar], list[Calendar]]:
    my_calendars: list[Calendar] = []
    other_calendars: list[Calendar] = []

    for calendar in calendars:
        if calendar.hidden:
            continue

        label = (calendar.summary_override or calendar.summary or "").lower()
        if "holiday" in label:
            other_calendars.append(calendar)
            continue

        if "birthday" in label or "task" in label or calendar.is_primary or calendar.selected:
            my_calendars.append(calendar)
            continue

        other_calendars.append(calendar)

    if not other_calendars:
        return my_calendars, []

    return my_calendars, other_calendars


templates.env.globals["cal_color"] = _cal_color
templates.env.globals["cal_text_color"] = _cal_text_color
templates.env.globals["allowed_calendar_color_ids"] = ALLOWED_CALENDAR_COLOR_IDS
templates.env.globals["default_calendar_color_id"] = DEFAULT_CALENDAR_COLOR_ID
templates.env.globals["canonical_calendar_color_id"] = canonical_calendar_color_id
templates.env.filters["fromjson"] = json.loads

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_FIXTURES_DIR = _PROJECT_ROOT / "tests" / "fixtures" / "real_gcal"
_SPEC_PATH = _PROJECT_ROOT / "tests" / "fixtures" / "gcal_api_spec.json"
_COVERAGE_PATH = _PROJECT_ROOT / "tests" / "fixtures" / "mock_coverage.json"

_spec_cache: dict | None = None
_coverage_cache: dict | None = None

# ─── Calendar helpers ─────────────────────────────────────────────────────────

def _get_week_dates(anchor: date) -> list[date]:
    """Return 7 dates Sun–Sat for the week containing anchor."""
    sun_offset = (anchor.weekday() + 1) % 7   # Mon=0,Sun=6 → Sun=0 offset
    week_start = anchor - timedelta(days=sun_offset)
    return [week_start + timedelta(days=i) for i in range(7)]


def _get_mini_cal(year: int, month: int) -> dict:
    """Generate mini calendar data (Sun-start weeks)."""
    cal = _cal_mod.Calendar(firstweekday=6)   # Sun first
    weeks = cal.monthdatescalendar(year, month)
    prev = date(year, month, 1) - timedelta(days=1)
    nxt_month = month % 12 + 1
    nxt_year = year + (1 if month == 12 else 0)
    return {
        "year": year, "month": month,
        "month_name": _MONTH_NAMES[month],
        "weeks": weeks,
        "prev_year": prev.year, "prev_month": prev.month,
        "next_year": nxt_year, "next_month": nxt_month,
    }


def _assign_overlap_layout(events: list[dict]) -> None:
    """Mutate event dicts in-place, adding ``left_pct`` and ``width_pct``.

    Uses greedy interval graph coloring so overlapping events in the same day
    column are laid out side-by-side (standard GCal behaviour).
    """
    if not events:
        return
    evs = sorted(events, key=lambda e: e["start_minutes"])
    col_end: list[int] = []  # col_end[i] = end-minute of last event placed in column i
    for ev in evs:
        start = ev["start_minutes"]
        end = start + ev["duration_minutes"]
        placed = False
        for i, end_t in enumerate(col_end):
            if start >= end_t:
                ev["_col"] = i
                col_end[i] = end
                placed = True
                break
        if not placed:
            ev["_col"] = len(col_end)
            col_end.append(end)
    # For each event determine how many columns exist in its overlap cluster.
    for ev in evs:
        ev_s = ev["start_minutes"]
        ev_e = ev_s + ev["duration_minutes"]
        max_col = ev["_col"]
        for other in evs:
            if other is ev:
                continue
            if ev_s < other["start_minutes"] + other["duration_minutes"] and ev_e > other["start_minutes"]:
                max_col = max(max_col, other["_col"])
        ev["_n_cols"] = max_col + 1
    for ev in evs:
        col = ev.pop("_col")
        n = ev.pop("_n_cols")
        ev["left_pct"] = round(col / n * 100, 4)
        ev["width_pct"] = round(100 / n, 4)


def _build_week_events(
    events: list,
    week_dates: list[date],
    cal_color_map: dict[str, str],
    cal_name_map: dict[str, str] | None = None,
    viewer_email: str | None = None,
    display_tz: timezone | zoneinfo.ZoneInfo = timezone.utc,
    hour_px: int = _UI_HOUR_PX,
) -> tuple[dict, dict]:
    """
    Returns:
        timed_by_date:   {date_iso: [event_dict, ...]}
        allday_by_date:  {date_iso: [event_dict, ...]}

    Each timed event dict includes ``left_pct`` / ``width_pct`` for overlap
    layout and ``is_continuation`` to mark cross-midnight continuations.
    """
    timed_by_date: dict[str, list] = {d.isoformat(): [] for d in week_dates}
    allday_by_date: dict[str, list] = {d.isoformat(): [] for d in week_dates}
    names = cal_name_map or {}

    for ev in events:
        color = cal_color_map.get(ev.calendar_id, "#4986e7")
        try:
            attendees = json.loads(ev.attendees_json or "[]")
        except Exception:
            attendees = []
        viewer_response = _viewer_response(attendees, viewer_email)
        visual_state = _event_visual_state(ev.status, viewer_response)

        if ev.start_is_date:
            start_dt = ev.start_dt
            end_dt = ev.end_dt
        else:
            start_dt = ev.start_dt.astimezone(display_tz)
            end_dt = ev.end_dt.astimezone(display_tz)

        base = {
            "id": ev.id,
            "summary": ev.summary or "(No title)",
            "calendar_id": ev.calendar_id,
            "calendar_name": names.get(ev.calendar_id, ""),
            "color": color,
            "status": ev.status,
            "viewer_response": viewer_response or "",
            "visual_state": visual_state,
            "location": ev.location or "",
            "attendees": attendees,
            "attendees_json": json.dumps(attendees, separators=(",", ":")),
            "description": ev.description or "",
            "start_iso": start_dt.strftime("%Y-%m-%dT%H:%M"),
            "end_iso":   end_dt.strftime("%Y-%m-%dT%H:%M"),
            "start_str": start_dt.strftime("%-I:%M %p") if not ev.start_is_date else "",
            "end_str": end_dt.strftime("%-I:%M %p") if not ev.start_is_date else "",
            "card_time": _format_compact_time_range(start_dt, end_dt) if not ev.start_is_date else "",
        }
        if ev.start_is_date:
            # All-day: add to every day it covers within the week.
            for d in week_dates:
                if start_dt.date() <= d < end_dt.date():
                    allday_by_date[d.isoformat()].append(base)
        else:
            start_date = start_dt.date()
            end_date = end_dt.date()
            # Iterate over each day of the week the event spans.
            cur_date = max(start_date, week_dates[0])
            while cur_date <= end_date and cur_date <= week_dates[-1]:
                is_start = cur_date == start_date
                is_end = cur_date == end_date
                seg_start_min = (start_dt.hour * 60 + start_dt.minute) if is_start else 0
                seg_end_min = (end_dt.hour * 60 + end_dt.minute) if is_end else 24 * 60
                # Event ends at midnight of this continuation day — nothing to render.
                if seg_end_min == 0 and not is_start:
                    break
                dur_min = max(30, seg_end_min - seg_start_min)
                clipped = min(dur_min, 24 * 60 - seg_start_min)
                timed_by_date[cur_date.isoformat()].append({
                    **base,
                    "start_minutes": seg_start_min,
                    "duration_minutes": clipped,
                    "top_px": round(seg_start_min * hour_px / 60),
                    "height_px": max(round(clipped * hour_px / 60), 18),
                    "is_continuation": not is_start,
                })
                cur_date += timedelta(days=1)

    for day_iso in timed_by_date:
        _assign_overlap_layout(timed_by_date[day_iso])

    return timed_by_date, allday_by_date


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _get_current_user(db: Session, request: Request) -> User | None:
    user_id = request.cookies.get("mock_gcal_user", "")
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return user
    return db.query(User).first()


def _get_calendars(db: Session, user: User | None) -> list:
    if not user:
        return []
    return db.query(Calendar).filter(Calendar.user_id == user.id).all()


def _get_db_stats(db: Session, user_id: str) -> dict:
    return {
        "calendars": db.query(Calendar).filter(Calendar.user_id == user_id).count(),
        "events": db.query(Event).filter(Event.user_id == user_id).count(),
        "acl_rules": (
            db.query(AclRule)
            .join(Calendar, Calendar.id == AclRule.calendar_id)
            .filter(Calendar.user_id == user_id)
            .count()
        ),
    }


def _load_spec() -> dict:
    global _spec_cache
    if _spec_cache is None:
        _spec_cache = json.loads(_SPEC_PATH.read_text())
    return _spec_cache


def _load_coverage() -> dict:
    global _coverage_cache
    if _coverage_cache is None:
        _coverage_cache = json.loads(_COVERAGE_PATH.read_text())
    return _coverage_cache


def _build_coverage_summary() -> dict:
    spec = _load_spec()
    coverage = _load_coverage()
    cov_by_id = {ep["id"]: ep for ep in coverage.get("endpoints", [])}

    summary: dict[str, dict] = {}
    for resource, data in spec.get("resources", {}).items():
        endpoints = []
        mock_count = 0
        tested_count = 0
        fixture_count = 0

        for endpoint in data.get("endpoints", []):
            cov = cov_by_id.get(endpoint["id"], {})
            implemented = bool(cov.get("implemented"))
            tests = cov.get("tests", [])
            fixture = cov.get("fixture")
            skip_reason = cov.get("skip_reason")

            if implemented:
                mock_count += 1
            if tests:
                tested_count += 1
            if fixture:
                fixture_count += 1

            endpoints.append({
                "id": endpoint["id"],
                "method": endpoint["method"],
                "path": endpoint["path"],
                "implemented": implemented,
                "fixture": fixture,
                "tests": tests,
                "skip_reason": skip_reason,
            })

        total = len(data.get("endpoints", []))
        summary[resource] = {
            "gcal_count": total,
            "mock_count": mock_count,
            "tested_count": tested_count,
            "fixture_count": fixture_count,
            "pct": round(mock_count / total * 100) if total else 0,
            "endpoints": endpoints,
        }

    return summary


def _get_test_inventory() -> dict:
    tests_dir = _PROJECT_ROOT / "tests"
    inventory: dict[str, dict] = {}
    total = 0
    if not tests_dir.is_dir():
        return {"files": {}, "total": 0}

    for test_file in sorted(tests_dir.glob("test_*.py")):
        filename = test_file.name
        content = test_file.read_text()
        tree = ast.parse(content, filename=filename)
        classes: dict[str, list[str]] = {}
        module_tests: list[str] = []
        file_count = 0

        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                module_tests.append(node.name)
                file_count += 1
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                class_tests = [
                    child.name
                    for child in node.body
                    if isinstance(child, ast.FunctionDef) and child.name.startswith("test_")
                ]
                if class_tests:
                    classes[node.name] = class_tests
                    file_count += len(class_tests)

        inventory[filename] = {
            "classes": classes,
            "module_tests": module_tests,
            "count": file_count,
        }
        total += file_count

    return {"files": inventory, "total": total}


def _count_fields(data) -> int:
    if isinstance(data, dict):
        return len(data)
    return 0


def _get_fixtures_info() -> list[dict]:
    coverage = _load_coverage()
    fixture_endpoints: dict[str, list[str]] = {}
    fixture_tests: dict[str, list[str]] = {}

    for endpoint in coverage.get("endpoints", []):
        fixture = endpoint.get("fixture")
        if not fixture:
            continue
        fixture_endpoints.setdefault(fixture, []).append(endpoint["id"])
        fixture_tests.setdefault(fixture, []).extend(endpoint.get("tests", []))

    fixtures = []
    if not _FIXTURES_DIR.is_dir():
        return fixtures

    for fixture_path in sorted(_FIXTURES_DIR.glob("*.json")):
        if fixture_path.name.startswith("_"):
            continue
        try:
            data = json.loads(fixture_path.read_text())
            field_count = _count_fields(data)
        except (json.JSONDecodeError, ValueError):
            field_count = 0

        tests = sorted(set(fixture_tests.get(fixture_path.name, [])))
        fixtures.append({
            "name": fixture_path.name,
            "size": fixture_path.stat().st_size,
            "endpoint": ", ".join(fixture_endpoints.get(fixture_path.name, [])),
            "tests": tests,
            "field_count": field_count,
        })

    return fixtures


def _run_pytest() -> dict | None:
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "--tb=short", "-q",
             "--json-report", "--json-report-file=-"],
            capture_output=True, text=True, timeout=120, cwd=str(_PROJECT_ROOT),
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return json.loads(result.stdout)
    except Exception:
        return None


def _parse_test_results(report: dict) -> dict:
    tests = report.get("tests", [])
    summary = report.get("summary", {})
    grouped: dict = {}
    for t in tests:
        nodeid = t.get("nodeid", "")
        filename = nodeid.split("::")[0] if "::" in nodeid else nodeid
        testname = nodeid.split("::")[-1] if "::" in nodeid else nodeid
        outcome = t.get("outcome", "unknown")
        longrepr = t.get("call", {}).get("longrepr", "") if outcome == "failed" else ""
        if filename not in grouped:
            grouped[filename] = {"tests": [], "passed": 0, "failed": 0, "skipped": 0}
        grouped[filename]["tests"].append({
            "name": testname, "outcome": outcome,
            "duration": round(t.get("duration", 0), 3), "longrepr": longrepr,
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


def _build_dashboard_context(request: Request, db: Session, test_results=None) -> dict:
    user = _get_current_user(db, request)
    db_stats = _get_db_stats(db, user.id) if user else {"calendars": 0, "events": 0, "acl_rules": 0}
    coverage_summary = _build_coverage_summary()
    test_inventory = _get_test_inventory()
    fixtures = _get_fixtures_info()
    actions = action_log.get_entries()

    total_gcal = sum(item["gcal_count"] for item in coverage_summary.values())
    total_mock = sum(item["mock_count"] for item in coverage_summary.values())
    impl_pct = round(total_mock / total_gcal * 100) if total_gcal else 0

    return {
        "request": request,
        "user": user,
        "db_stats": db_stats,
        "calendars": _get_calendars(db, user),
        "snapshots": list_snapshot_names(),
        "coverage_summary": coverage_summary,
        "total_gcal": total_gcal,
        "total_mock": total_mock,
        "impl_pct": impl_pct,
        "fixtures": fixtures,
        "fixture_count": len(fixtures),
        "total_fixtures": len(fixtures),
        "test_inventory": test_inventory,
        "test_results": test_results,
        "action_log": actions[-50:],
        "action_count": len(actions),
    }


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def calendar_view(
    request: Request,
    week: str = Query("", alias="week"),
    cal: str = Query("", alias="cal"),
    mini_year: int = Query(0, alias="mini_year"),
    mini_month: int = Query(0, alias="mini_month"),
    db: Session = Depends(get_db),
):
    user = _get_current_user(db, request)
    if not user:
        return HTMLResponse("<h1>No users. Run <code>mock-gcal seed</code></h1>")

    try:
        display_tz = zoneinfo.ZoneInfo(user.timezone)
    except Exception:
        display_tz = timezone.utc

    now = datetime.now(display_tz)
    today = now.date()

    # Parse week anchor
    try:
        anchor = date.fromisoformat(week) if week else today
    except ValueError:
        anchor = today

    week_dates = _get_week_dates(anchor)
    week_start_dt = datetime.combine(week_dates[0], time.min, tzinfo=display_tz).astimezone(timezone.utc)
    week_end_dt = datetime.combine(week_dates[-1] + timedelta(days=1), time.min, tzinfo=display_tz).astimezone(timezone.utc)
    month_heading = f"{_MONTH_NAMES[anchor.month]} {anchor.year}"

    # Navigation
    prev_week = (week_dates[0] - timedelta(days=7)).isoformat()
    next_week = (week_dates[0] + timedelta(days=7)).isoformat()

    # Week label  e.g. "January 5 – 11, 2026"
    ws, we = week_dates[0], week_dates[-1]
    if ws.month == we.month:
        week_label = f"{_MONTH_NAMES[ws.month]} {ws.day} – {we.day}, {ws.year}"
    else:
        week_label = f"{_MONTH_NAMES[ws.month]} {ws.day} – {_MONTH_NAMES[we.month]} {we.day}, {ws.year}"

    # Fetch events for the week
    calendars = db.query(Calendar).filter(Calendar.user_id == user.id).all()
    cal_color_map = {c.id: _cal_color(c.color_id) for c in calendars}
    cal_name_map = {c.id: c.summary for c in calendars}
    my_calendars, other_calendars = _partition_sidebar_calendars(calendars)

    q = db.query(Event).filter(
        Event.user_id == user.id,
        Event.start_dt < week_end_dt,
        Event.end_dt > week_start_dt,
    )
    if cal:
        q = q.filter(Event.calendar_id == cal)
    events = q.order_by(Event.start_dt.asc()).all()

    timed_by_date, allday_by_date = _build_week_events(
        events,
        week_dates,
        cal_color_map,
        cal_name_map,
        viewer_email=user.email_address,
        display_tz=display_tz,
        hour_px=_UI_HOUR_PX,
    )

    # Mini calendar (sidebar)
    mc_year = mini_year or anchor.year
    mc_month = mini_month or anchor.month
    mini_cal = _get_mini_cal(mc_year, mc_month)

    db_stats = _get_db_stats(db, user.id)

    tz_offset_label = _format_gmt_offset_label(now.utcoffset(), with_minutes=False)
    tz_editor_offset_label = _format_gmt_offset_label(now.utcoffset(), with_minutes=True)
    tz_editor_city_label = _friendly_timezone_label(getattr(display_tz, "key", "UTC"))
    page_state = {
        "today": today.isoformat(),
        "week_start": week_dates[0].isoformat(),
        "week_end_exclusive": (week_dates[-1] + timedelta(days=1)).isoformat(),
        "timezone": getattr(display_tz, "key", "UTC"),
        "tz_abbr": tz_offset_label,
    }

    return templates.TemplateResponse(request, "calendar.html", context={
        "user": user,
        "calendars": calendars,
        "my_calendars": my_calendars,
        "other_calendars": other_calendars,
        "week_dates": week_dates,
        "timed_by_date": timed_by_date,
        "allday_by_date": allday_by_date,
        "today": today,
        "now": now,
        "prev_week": prev_week,
        "next_week": next_week,
        "week_label": week_label,
        "month_heading": month_heading,
        "cur_cal": cal,
        "db_stats": db_stats,
        "mini_cal": mini_cal,
        "day_abbr": _DAY_ABBR,
        "month_names": _MONTH_NAMES,
        "tz_abbr": tz_offset_label,
        "tz_editor_offset_label": tz_editor_offset_label,
        "tz_editor_city_label": tz_editor_city_label,
        "hour_px": _UI_HOUR_PX,
        "page_state": page_state,
    })


@router.get("/dev/db-viewer", response_class=HTMLResponse)
def db_viewer(
    request: Request,
    table: str = Query("events", alias="table"),
    page: int = Query(1, alias="page"),
    db: Session = Depends(get_db),
):
    user = _get_current_user(db, request)
    db_stats = _get_db_stats(db, user.id) if user else {}
    per_page = 25
    offset = (page - 1) * per_page
    rows: list[dict] = []
    columns: list[str] = []
    total = 0

    if table == "events":
        columns = ["id", "calendar_id", "summary", "status", "start_dt", "end_dt", "location", "attendees"]
        total = db.query(Event).filter(Event.user_id == user.id).count() if user else 0
        items = (db.query(Event).filter(Event.user_id == user.id)
                 .order_by(Event.start_dt.desc()).offset(offset).limit(per_page).all()) if user else []
        for e in items:
            rows.append({
                "id": e.id, "calendar_id": e.calendar_id,
                "summary": e.summary[:60] + ("..." if len(e.summary) > 60 else ""),
                "status": e.status,
                "start_dt": e.start_dt.strftime("%Y-%m-%d %H:%M") if e.start_dt else "",
                "end_dt": e.end_dt.strftime("%Y-%m-%d %H:%M") if e.end_dt else "",
                "location": (e.location[:40] + "..." if len(e.location) > 40 else e.location) if e.location else "",
                "attendees": len(json.loads(e.attendees_json or "[]")),
            })
    elif table == "calendars":
        columns = ["id", "summary", "access_role", "primary", "selected", "color_id", "timezone"]
        total = db.query(Calendar).filter(Calendar.user_id == user.id).count() if user else 0
        items = (db.query(Calendar).filter(Calendar.user_id == user.id)
                 .offset(offset).limit(per_page).all()) if user else []
        for c in items:
            rows.append({"id": c.id, "summary": c.summary, "access_role": c.access_role,
                         "primary": c.is_primary, "selected": c.selected,
                         "color_id": c.color_id, "timezone": c.timezone})
    elif table == "acl_rules":
        columns = ["id", "calendar_id", "scope_type", "scope_value", "role"]
        base_q = (db.query(AclRule).join(Calendar, Calendar.id == AclRule.calendar_id)
                  .filter(Calendar.user_id == user.id)) if user else db.query(AclRule).filter(False)
        total = base_q.count()
        for r in base_q.offset(offset).limit(per_page).all():
            rows.append({"id": r.id, "calendar_id": r.calendar_id,
                         "scope_type": r.scope_type, "scope_value": r.scope_value, "role": r.role})
    elif table == "users":
        columns = ["id", "email_address", "display_name", "timezone", "history_id"]
        total = db.query(User).count()
        for u in db.query(User).offset(offset).limit(per_page).all():
            rows.append({"id": u.id, "email_address": u.email_address,
                         "display_name": u.display_name, "timezone": u.timezone,
                         "history_id": u.history_id})

    total_pages = max(1, (total + per_page - 1) // per_page)
    return templates.TemplateResponse(request, "db_viewer.html", context={
        "user": user, "db_stats": db_stats,
        "calendars": _get_calendars(db, user),
        "table": table, "columns": columns, "rows": rows,
        "total": total, "page": page, "total_pages": total_pages,
        "tables": ["events", "calendars", "acl_rules", "users"],
    })


@router.get("/dev/api-explorer", response_class=HTMLResponse)
def api_explorer(request: Request, db: Session = Depends(get_db)):
    user = _get_current_user(db, request)
    db_stats = _get_db_stats(db, user.id) if user else {}
    sample_cal = db.query(Calendar).filter(Calendar.user_id == user.id).first() if user else None
    sample_event = db.query(Event).filter(Event.user_id == user.id).first() if user else None
    return templates.TemplateResponse(request, "api_explorer.html", context={
        "user": user, "db_stats": db_stats,
        "calendars": _get_calendars(db, user),
        "sample_cal_id": sample_cal.id if sample_cal else "primary",
        "sample_event_id": sample_event.id if sample_event else "evt_user1_00001",
        "user_id": user.id if user else "me",
    })


@router.get("/dev/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "dashboard.html", context=_build_dashboard_context(request, db))


@router.post("/dev/dashboard/run-tests", response_class=HTMLResponse)
def run_tests(request: Request, db: Session = Depends(get_db)):
    report = _run_pytest()
    context = _build_dashboard_context(
        request,
        db,
        test_results=_parse_test_results(report) if report else None,
    )
    return templates.TemplateResponse(request, "dashboard_body.html", context=context)


@router.post("/dev/dashboard/snapshot")
async def dashboard_snapshot_save(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    if name:
        take_snapshot(name)
    return RedirectResponse("/dev/dashboard", status_code=303)


@router.post("/dev/dashboard/restore")
async def dashboard_snapshot_restore(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    if name:
        restore_snapshot(name)
    return RedirectResponse("/dev/dashboard", status_code=303)

