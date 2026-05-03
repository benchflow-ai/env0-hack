"""Env-owned seed packs layered onto reusable base scenarios.

Timezone rules for seed event templates
----------------------------------------
- start_iso / end_iso: Always UTC (Z suffix). Hours are stored as-is.
- start_hour with weekday / days_from_now / start_date: Interpreted as
  LOCAL time in the user's timezone (America/Los_Angeles), then converted
  to UTC for storage. Use this for "office hours" style events.

Do NOT put a UTC hour into start_hour and expect it to be stored as UTC.
If you need an exact UTC time, use start_iso instead.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass


@dataclass(frozen=True)
class SeedPack:
    name: str
    needle_events: tuple[dict, ...] = ()
    recurring_needles: tuple[dict, ...] = ()


def _pack(
    name: str,
    *,
    needle_events: list[dict] | None = None,
    recurring_needles: list[dict] | None = None,
) -> SeedPack:
    return SeedPack(
        name=name,
        needle_events=tuple(deepcopy(needle_events or [])),
        recurring_needles=tuple(deepcopy(recurring_needles or [])),
    )


def clone_pack_events(pack: SeedPack) -> tuple[list[dict], list[dict]]:
    return (
        [deepcopy(event) for event in pack.needle_events],
        [deepcopy(event) for event in pack.recurring_needles],
    )


def get_seed_pack(name: str) -> SeedPack:
    try:
        return _PACKS[name]
    except KeyError as exc:
        available = ", ".join(sorted(_PACKS))
        raise ValueError(f"Unknown gcal seed pack: {name!r}. Available: {available}") from exc


def list_seed_packs() -> list[str]:
    return sorted(_PACKS)


def _sync_event(event: dict, existing_event: dict | None = None) -> dict:
    merged = deepcopy(event)
    if existing_event:
        merged.update(deepcopy(existing_event))
    return merged


FOSDEM_2023_AMENDMENT_SEED_EVENTS = [
    {
        "summary": "CANCELLED Eliminating ManagedStatic and llvm_shutdown",
        "start_iso": "2023-02-04T14:50:00Z",
        "end_iso": "2023-02-04T15:00:00Z",
        "location": "AW1.120",
        "description": "https://archive.fosdem.org/2023/schedule/event/llvmglobalstate/",
        "calendar": "primary",
    },
    {
        "summary": "CANCELLED GRUB - Project Status Update",
        "start_iso": "2023-02-05T08:10:00Z",
        "end_iso": "2023-02-05T08:35:00Z",
        "location": "K.4.201",
        "description": "https://archive.fosdem.org/2023/schedule/event/grub_status_update/",
        "calendar": "primary",
    },
    {
        "summary": "CANCELLED Container Storage Interface Addons",
        "start_iso": "2023-02-04T15:30:00Z",
        "end_iso": "2023-02-04T16:05:00Z",
        "location": "D.sds (online)",
        "description": "https://archive.fosdem.org/2023/schedule/event/sds_csi_addons/",
        "calendar": "primary",
    },
    {
        "summary": "CANCELLED Monitoring and Centralized Logging in Ceph",
        "start_iso": "2023-02-04T16:05:00Z",
        "end_iso": "2023-02-04T16:40:00Z",
        "location": "D.sds (online)",
        "description": "https://archive.fosdem.org/2023/schedule/event/sds_monitoring_ceph/",
        "calendar": "primary",
    },
    {
        "summary": "CANCELLED First class support in OSS",
        "start_iso": "2023-02-04T16:45:00Z",
        "end_iso": "2023-02-04T17:25:00Z",
        "location": "H.2214",
        "description": "https://archive.fosdem.org/2023/schedule/event/sds_first_class_support/",
        "calendar": "primary",
    },
    {
        "summary": "AMENDMENT Autoscaling with KEDA - Object Store Case Study",
        "start_iso": "2023-02-04T15:30:00Z",
        "end_iso": "2023-02-04T15:55:00Z",
        "location": "H.2214",
        "description": "https://archive.fosdem.org/2023/schedule/event/sds_keda_object_store/",
        "calendar": "primary",
    },
    {
        "summary": "Ceph RGW: S3 Select & Pushdown",
        "start_iso": "2023-02-04T14:30:00Z",
        "end_iso": "2023-02-04T15:05:00Z",
        "location": "D.sds (online)",
        "description": "https://archive.fosdem.org/2023/schedule/event/sds_ceph_rgw_s3select/",
        "calendar": "primary",
    },
    {
        "summary": "CANCELLED Network Performance in the Linux Kernel",
        "start_iso": "2023-02-04T13:00:00Z",
        "end_iso": "2023-02-04T13:50:00Z",
        "location": "H.1308 (Rolin)",
        "description": "https://archive.fosdem.org/2023/schedule/event/network_performance_in_kernel/",
        "calendar": "primary",
    },
]


IETF_INTERIM_CANCELLED_SESSION_SEED_EVENTS = [
    {
        "summary": "cbor - Concise Binary Object Representation Maintenance and Extensions",
        "start_iso": "2024-10-02T14:00:00Z",
        "end_iso": "2024-10-02T15:00:00Z",
        "location": "",
        "description": "https://datatracker.ietf.org/meeting/interim-2024-cbor-16/session/cbor",
        "calendar": "primary",
    },
    {
        "summary": "moq - Media Over QUIC (We are not ready to build an agenda at this time.)",
        "start_iso": "2025-01-08T17:00:00Z",
        "end_iso": "2025-01-08T18:00:00Z",
        "location": "",
        "description": "https://datatracker.ietf.org/meeting/interim-2025-moq-05/session/moq",
        "calendar": "primary",
    },
    {
        "summary": "idr - Inter-Domain Routing (Interim canceled due to lack of presentations.)",
        "start_iso": "2024-06-24T14:00:00Z",
        "end_iso": "2024-06-24T17:00:00Z",
        "location": "",
        "description": "https://datatracker.ietf.org/meeting/interim-2024-idr-05/session/idr",
        "calendar": "primary",
    },
    {
        "summary": "core - Constrained RESTful Environments",
        "start_iso": "2026-02-25T15:00:00Z",
        "end_iso": "2026-02-25T16:30:00Z",
        "location": "",
        "description": "https://datatracker.ietf.org/meeting/interim-2026-core-04/session/core",
        "calendar": "primary",
    },
    {
        "summary": "cbor - Concise Binary Object Representation Maintenance and Extensions",
        "start_iso": "2024-10-16T14:00:00Z",
        "end_iso": "2024-10-16T15:00:00Z",
        "location": "",
        "description": "https://datatracker.ietf.org/meeting/interim-2024-cbor-17/session/cbor",
        "calendar": "primary",
    },
    {
        "summary": "moq - Media Over QUIC",
        "start_iso": "2025-01-22T17:00:00Z",
        "end_iso": "2025-01-22T18:00:00Z",
        "location": "",
        "description": "https://datatracker.ietf.org/meeting/interim-2025-moq-06/session/moq",
        "calendar": "primary",
    },
    {
        "summary": "idr - Inter-Domain Routing (https://trac.ietf.org/trac/idr/wiki/)",
        "start_iso": "2024-06-03T14:00:00Z",
        "end_iso": "2024-06-03T15:30:00Z",
        "location": "",
        "description": "https://datatracker.ietf.org/meeting/interim-2024-idr-08/session/idr",
        "calendar": "primary",
    },
    {
        "summary": "core - Constrained RESTful Environments",
        "start_iso": "2026-02-11T15:00:00Z",
        "end_iso": "2026-02-11T16:30:00Z",
        "location": "",
        "description": "https://datatracker.ietf.org/meeting/interim-2026-core-03/session/core",
        "calendar": "primary",
    },
]


FEDERAL_REGISTER_MEETING_AMENDMENT_SEED_EVENTS = [
    {
        "summary": "Gateway National Recreation Area Fort Hancock 21st Century Advisory Committee Notice of Public Meetings",
        "start_iso": "2025-01-15T14:00:00Z",
        "end_iso": "2025-01-15T19:00:00Z",
        "location": "Virtual",
        "description": (
            "https://www.federalregister.gov/documents/2024/10/03/2024-22761/"
            "gateway-national-recreation-area-fort-hancock-21st-century-advisory-committee-notice-of-public"
        ),
        "calendar": "primary",
    },
    {
        "summary": "Notice of Public Meeting for the National Park System Advisory Board",
        "start_iso": "2024-03-07T17:00:00Z",
        "end_iso": "2024-03-08T01:00:00Z",
        "location": "At or near Joshua Tree National Park, California",
        "description": (
            "https://www.federalregister.gov/documents/2023/12/28/2023-28710/"
            "notice-of-public-meeting-for-the-national-park-system-advisory-board"
        ),
        "calendar": "primary",
    },
    {
        "summary": "Notice of Public Meeting for the National Park System Advisory Board",
        "start_iso": "2024-03-08T17:00:00Z",
        "end_iso": "2024-03-09T01:00:00Z",
        "location": "At or near Joshua Tree National Park, California",
        "description": (
            "https://www.federalregister.gov/documents/2023/12/28/2023-28710/"
            "notice-of-public-meeting-for-the-national-park-system-advisory-board"
        ),
        "calendar": "primary",
    },
    {
        "summary": "Gateway National Recreation Area Fort Hancock 21st Century Advisory Committee Notice of Public Meetings",
        "start_iso": "2025-05-08T13:00:00Z",
        "end_iso": "2025-05-08T18:00:00Z",
        "location": "Virtual",
        "description": (
            "https://www.federalregister.gov/documents/2024/10/03/2024-22761/"
            "gateway-national-recreation-area-fort-hancock-21st-century-advisory-committee-notice-of-public"
        ),
        "calendar": "primary",
    },
    {
        "summary": "Gateway National Recreation Area Fort Hancock 21st Century Advisory Committee Notice of Public Meetings",
        "start_iso": "2025-10-10T13:00:00Z",
        "end_iso": "2025-10-10T18:00:00Z",
        "location": "Virtual",
        "description": (
            "https://www.federalregister.gov/documents/2024/10/03/2024-22761/"
            "gateway-national-recreation-area-fort-hancock-21st-century-advisory-committee-notice-of-public"
        ),
        "calendar": "primary",
    },
]


MULTI_MAIL_CAL_SYNC_ACTION_SEED_EVENTS = [
    _sync_event(
        {
            "summary": "1:1 with Sarah",
            "weekday": 2,
            "start_hour": 16,
            "duration_hours": 0.5,
            "location": "Room 3B",
            "description": "Weekly sync with manager.",
            "attendees": ["sarah"],
            "calendar": "primary",
        },
        {"start_hour": 10},
    ),
    _sync_event(
        {
            "summary": "Design Review with Priya",
            "weekday": 3,
            "start_hour": 15,
            "duration_hours": 1,
            "location": "Conference Room C",
            "description": "Review new dashboard mockups.",
            "attendees": ["priya"],
            "calendar": "primary",
        },
        {"start_hour": 14},
    ),
    _sync_event(
        {
            "summary": "Board Prep Session",
            "weekday": 4,
            "start_hour": 10,
            "duration_hours": 1.5,
            "location": "Conference Room A",
            "description": "Prepare materials for quarterly board meeting.",
            "attendees": ["victor", "sarah"],
            "calendar": "primary",
        },
        {"location": "Conference Room B"},
    ),
    {
        "summary": "Friday Drinks",
        "weekday": 4,
        "start_hour": 18,
        "duration_hours": 2,
        "location": "Zeitgeist",
        "description": "Team happy hour.",
        "attendees": ["james", "marcus"],
        "calendar": "primary",
    },
    {
        "summary": "Client Call — Acme Corp",
        "weekday": 0,
        "start_hour": 15,
        "duration_hours": 1,
        "location": "Zoom",
        "description": "Quarterly check-in with Acme team.",
        "attendees": ["nina"],
        "calendar": "primary",
    },
    {
        "summary": "Coffee with Dana",
        "start_hour": 15,
        "duration_hours": 1,
        "location": "Blue Bottle, Mint St",
        "description": "Catch up over coffee.",
        "calendar": "primary",
        "days_from_now": -5,
    },
    {
        "summary": "Yoga Class",
        "weekday": 2,
        "start_hour": 18,
        "duration_hours": 1,
        "location": "FitLife Gym",
        "description": "Hatha yoga at the gym.",
        "calendar": "primary",
    },
    {
        "summary": "Daily Standup",
        "start_hour": 9.25,
        "duration_hours": 0.25,
        "location": "Zoom",
        "description": "Team standup — status updates.",
        "calendar": "primary",
        "days_from_now": 0,
        "recurrence": ["RRULE:FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR;COUNT=10"],
    },
]


MULTI_MAIL_CAL_SYNC_WEEK_LAYOUT_EVENTS = [
    {"summary": "Sprint Planning", "weekday": 0, "week_offset": -1, "start_hour": 9.5, "duration_hours": 1.5, "location": "Room 2A", "description": "Plan sprint 22 backlog.", "attendees": ["marcus", "priya", "james"]},
    {"summary": "Focus Time — Deep Work", "weekday": 0, "week_offset": -1, "start_hour": 11, "duration_hours": 1, "location": "", "description": "No meetings block."},
    {"summary": "Lunch Hold", "weekday": 0, "week_offset": -1, "start_hour": 12, "duration_hours": 1, "location": "", "description": ""},
    {"summary": "API Migration Review", "weekday": 0, "week_offset": -1, "start_hour": 13.5, "duration_hours": 1, "location": "Room 3B", "description": "Review v2 → v3 migration plan.", "attendees": ["james", "omar"]},
    {"summary": "Incident Debrief — Payments", "weekday": 0, "week_offset": -1, "start_hour": 15, "duration_hours": 1, "location": "Room 4A", "description": "Post-incident review: Stripe webhook failure.", "attendees": ["omar", "elena", "marcus"]},
    {"summary": "1:1 with Nina", "weekday": 0, "week_offset": -1, "start_hour": 16.5, "duration_hours": 0.5, "location": "Room 4A", "description": "Direct report check-in.", "attendees": ["nina"]},
    {"summary": "Product Sync", "weekday": 1, "week_offset": -1, "start_hour": 9.5, "duration_hours": 1, "location": "Room 4A", "description": "Weekly product team alignment.", "attendees": ["lisa", "nina"]},
    {"summary": "Customer Call — Initech", "weekday": 1, "week_offset": -1, "start_hour": 11, "duration_hours": 0.5, "location": "Zoom", "description": "Monthly sync with Initech."},
    {"summary": "Lunch Hold", "weekday": 1, "week_offset": -1, "start_hour": 12, "duration_hours": 1, "location": "", "description": ""},
    {"summary": "Vendor Demo — LaunchDarkly", "weekday": 1, "week_offset": -1, "start_hour": 13, "duration_hours": 1, "location": "Zoom", "description": "Feature flag platform evaluation.", "attendees": ["omar", "priya"]},
    {"summary": "Customer Call — Globex", "weekday": 1, "week_offset": -1, "start_hour": 14.5, "duration_hours": 1, "location": "Zoom", "description": "QBR with Globex Inc."},
    {"summary": "Interview — Senior Engineer", "weekday": 1, "week_offset": -1, "start_hour": 16, "duration_hours": 1, "location": "Meet Room A", "description": "Technical interview, round 2.", "attendees": ["maya"]},
    {"summary": "Morning Run", "weekday": 2, "week_offset": -1, "start_hour": 6.5, "duration_hours": 0.75, "location": "Embarcadero", "description": "5k around the Embarcadero."},
    {"summary": "Architecture Review", "weekday": 2, "week_offset": -1, "start_hour": 9.5, "duration_hours": 1.5, "location": "Room 2A", "description": "Event-driven migration design.", "attendees": ["james", "marcus", "omar"]},
    {"summary": "All Hands", "weekday": 2, "week_offset": -1, "start_hour": 11, "duration_hours": 1, "location": "Auditorium", "description": "Company-wide all hands meeting."},
    {"summary": "Lunch Hold", "weekday": 2, "week_offset": -1, "start_hour": 12, "duration_hours": 1, "location": "", "description": ""},
    {"summary": "Code Review Session", "weekday": 2, "week_offset": -1, "start_hour": 14, "duration_hours": 1, "location": "Room 3B", "description": "Review auth service PRs.", "attendees": ["james", "marcus"]},
    {"summary": "Security Review", "weekday": 2, "week_offset": -1, "start_hour": 15, "duration_hours": 1, "location": "Room 4A", "description": "Monthly security posture review.", "attendees": ["omar", "elena"]},
    {"summary": "Mentorship Session — Intern", "weekday": 2, "week_offset": -1, "start_hour": 16.5, "duration_hours": 0.5, "location": "Coffee Bar", "description": "Weekly check-in with summer intern.", "attendees": ["alex"]},
    {"summary": "Team Retro", "weekday": 3, "week_offset": -1, "start_hour": 10, "duration_hours": 1, "location": "Room 2A", "description": "Sprint retrospective.", "attendees": ["sarah", "marcus", "priya", "james", "lisa"]},
    {"summary": "1:1 with James", "weekday": 3, "week_offset": -1, "start_hour": 11, "duration_hours": 0.5, "location": "Room 3B", "description": "Direct report check-in.", "attendees": ["james"]},
    {"summary": "Lunch — Burritos with Priya", "weekday": 3, "week_offset": -1, "start_hour": 12, "duration_hours": 1, "location": "La Taqueria", "description": "Catch-up lunch."},
    {"summary": "Vendor Demo — DataDog", "weekday": 3, "week_offset": -1, "start_hour": 14, "duration_hours": 1, "location": "Zoom", "description": "Evaluate observability tooling.", "attendees": ["omar", "marcus"]},
    {"summary": "Focus Time — Writing", "weekday": 3, "week_offset": -1, "start_hour": 15, "duration_hours": 2, "location": "", "description": "RFC drafting block."},
    {"summary": "Standup", "weekday": 4, "week_offset": -1, "start_hour": 9.5, "duration_hours": 0.25, "location": "", "description": "Quick async standup."},
    {"summary": "Compliance Training", "weekday": 4, "week_offset": -1, "start_hour": 10, "duration_hours": 1, "location": "Zoom", "description": "Annual SOC2 compliance refresher."},
    {"summary": "Lunch Hold", "weekday": 4, "week_offset": -1, "start_hour": 12, "duration_hours": 1, "location": "", "description": ""},
    {"summary": "Sprint Demo", "weekday": 4, "week_offset": -1, "start_hour": 14, "duration_hours": 1, "location": "Auditorium", "description": "Demo sprint 21 deliverables.", "attendees": ["sarah", "marcus", "priya", "james", "lisa", "nina"]},
    {"summary": "Weekly Planning Review", "weekday": 4, "week_offset": -1, "start_hour": 16, "duration_hours": 0.5, "location": "Room 3B", "description": "Review last week's progress.", "attendees": ["sarah"]},
    {"summary": "Happy Hour", "weekday": 4, "week_offset": -1, "start_hour": 17, "duration_hours": 1.5, "location": "Zeitgeist", "description": "End-of-week team drinks."},
    {"summary": "Yoga Class", "weekday": 5, "week_offset": -1, "start_hour": 8, "duration_hours": 1, "location": "Yoga Studio on Valencia", "description": "Vinyasa flow."},
    {"summary": "Farmers Market Run", "weekday": 5, "week_offset": -1, "start_hour": 10, "duration_hours": 1.5, "location": "Ferry Building", "description": "Pick up produce."},
    {"summary": "Dinner — Elena's Birthday", "weekday": 5, "week_offset": -1, "start_hour": 19, "duration_hours": 2.5, "location": "Nopa", "description": "Birthday dinner for Elena."},
    {"summary": "Brunch with Alex", "weekday": 6, "week_offset": -1, "start_hour": 10.5, "duration_hours": 1.5, "location": "Zazie", "description": "Catch-up brunch."},
    {"summary": "Meal Prep", "weekday": 6, "week_offset": -1, "start_hour": 16, "duration_hours": 2, "location": "", "description": "Prep lunches for the week."},
    {"summary": "Call with Parents", "weekday": 6, "week_offset": -1, "start_hour": 18.5, "duration_hours": 0.5, "location": "", "description": "Weekly family call."},
    {"summary": "Sprint Planning", "weekday": 0, "start_hour": 9.5, "duration_hours": 1.5, "location": "Room 2A", "description": "Plan sprint 23 backlog.", "attendees": ["marcus", "priya", "james"]},
    {"summary": "Focus Time — Deep Work", "weekday": 0, "start_hour": 11, "duration_hours": 1, "location": "", "description": "No meetings block."},
    {"summary": "Lunch Hold", "weekday": 0, "start_hour": 12, "duration_hours": 1, "location": "", "description": ""},
    {"summary": "API Migration Review", "weekday": 0, "start_hour": 14, "duration_hours": 1, "location": "Room 3B", "description": "Review v2 → v3 migration plan.", "attendees": ["james", "omar"]},
    {"summary": "1:1 with Nina", "weekday": 0, "start_hour": 15.5, "duration_hours": 0.5, "location": "Room 4A", "description": "Direct report check-in.", "attendees": ["nina"]},
    {"summary": "Product Sync", "weekday": 1, "start_hour": 10, "duration_hours": 1, "location": "Room 4A", "description": "Weekly product team alignment.", "attendees": ["lisa", "nina"]},
    {"summary": "Customer Call — Globex", "weekday": 1, "start_hour": 14, "duration_hours": 1, "location": "Zoom", "description": "QBR with Globex Inc."},
    {"summary": "Lunch Hold", "weekday": 1, "start_hour": 12, "duration_hours": 1, "location": "", "description": ""},
    {"summary": "Interview — Senior Engineer", "weekday": 1, "start_hour": 16, "duration_hours": 1, "location": "Meet Room A", "description": "Technical interview, round 2.", "attendees": ["maya"]},
    {"summary": "Customer Call — Initech", "weekday": 1, "start_hour": 11, "duration_hours": 0.5, "location": "Zoom", "description": "Monthly sync with Initech."},
    {"summary": "All Hands", "weekday": 2, "start_hour": 11, "duration_hours": 1, "location": "Auditorium", "description": "Company-wide all hands meeting."},
    {"summary": "Lunch Hold", "weekday": 2, "start_hour": 12, "duration_hours": 1, "location": "", "description": ""},
    {"summary": "Code Review Session", "weekday": 2, "start_hour": 14, "duration_hours": 1, "location": "Room 3B", "description": "Review auth service PRs.", "attendees": ["james", "marcus"]},
    {"summary": "Security Review", "weekday": 2, "start_hour": 15, "duration_hours": 1, "location": "Room 4A", "description": "Monthly security posture review.", "attendees": ["omar", "elena"]},
    {"summary": "Team Retro", "weekday": 3, "start_hour": 10, "duration_hours": 1, "location": "Room 2A", "description": "Sprint retrospective.", "attendees": ["sarah", "marcus", "priya", "james", "lisa"]},
    {"summary": "1:1 with James", "weekday": 3, "start_hour": 11, "duration_hours": 0.5, "location": "Room 3B", "description": "Direct report check-in.", "attendees": ["james"]},
    {"summary": "Lunch Hold", "weekday": 3, "start_hour": 12, "duration_hours": 1, "location": "", "description": ""},
    {"summary": "Focus Time — Writing", "weekday": 3, "start_hour": 15, "duration_hours": 2, "location": "", "description": "RFC drafting block."},
    {"summary": "Morning Run", "weekday": 3, "start_hour": 6.5, "duration_hours": 0.75, "location": "Embarcadero", "description": "5k around the Embarcadero."},
    {"summary": "Sprint Demo", "weekday": 4, "start_hour": 14, "duration_hours": 1, "location": "Auditorium", "description": "Demo sprint 22 deliverables.", "attendees": ["sarah", "marcus", "priya", "james", "lisa", "nina"]},
    {"summary": "Lunch Hold", "weekday": 4, "start_hour": 12, "duration_hours": 1, "location": "", "description": ""},
    {"summary": "Weekly Planning Review", "weekday": 4, "start_hour": 16, "duration_hours": 0.5, "location": "Room 3B", "description": "Review this week's progress, plan next.", "attendees": ["sarah"]},
    {"summary": "Yoga Class", "weekday": 5, "start_hour": 8, "duration_hours": 1, "location": "Yoga Studio on Valencia", "description": "Vinyasa flow."},
    {"summary": "Farmers Market Run", "weekday": 5, "start_hour": 10, "duration_hours": 1.5, "location": "Ferry Building", "description": "Pick up produce for the week."},
    {"summary": "Meal Prep", "weekday": 6, "start_hour": 16, "duration_hours": 2, "location": "", "description": "Prep lunches for the week."},
    {"summary": "Call with Parents", "weekday": 6, "start_hour": 18.5, "duration_hours": 0.5, "location": "", "description": "Weekly family call."},
    {"summary": "Sprint Planning", "weekday": 0, "week_offset": 1, "start_hour": 9.5, "duration_hours": 1.5, "location": "Room 2A", "description": "Plan sprint 24 backlog.", "attendees": ["marcus", "priya", "james"]},
    {"summary": "Lunch Hold", "weekday": 0, "week_offset": 1, "start_hour": 12, "duration_hours": 1, "location": "", "description": ""},
    {"summary": "Perf Review Prep", "weekday": 0, "week_offset": 1, "start_hour": 14, "duration_hours": 1.5, "location": "Room 4A", "description": "Draft Q1 reviews for directs.", "attendees": ["sarah"]},
    {"summary": "Product Sync", "weekday": 1, "week_offset": 1, "start_hour": 10, "duration_hours": 1, "location": "Room 4A", "description": "Weekly product team alignment.", "attendees": ["lisa", "nina"]},
    {"summary": "Lunch Hold", "weekday": 1, "week_offset": 1, "start_hour": 12, "duration_hours": 1, "location": "", "description": ""},
    {"summary": "Onboarding — New Hire", "weekday": 1, "week_offset": 1, "start_hour": 15, "duration_hours": 1, "location": "Room 2A", "description": "Welcome and setup walkthrough.", "attendees": ["priya"]},
    {"summary": "All Hands", "weekday": 2, "week_offset": 1, "start_hour": 11, "duration_hours": 1, "location": "Auditorium", "description": "Company-wide all hands meeting."},
    {"summary": "Lunch Hold", "weekday": 2, "week_offset": 1, "start_hour": 12, "duration_hours": 1, "location": "", "description": ""},
    {"summary": "Team Retro", "weekday": 3, "week_offset": 1, "start_hour": 10, "duration_hours": 1, "location": "Room 2A", "description": "Sprint retrospective.", "attendees": ["sarah", "marcus", "priya", "james", "lisa"]},
    {"summary": "Lunch Hold", "weekday": 3, "week_offset": 1, "start_hour": 12, "duration_hours": 1, "location": "", "description": ""},
    {"summary": "Budget Review — Q2", "weekday": 3, "week_offset": 1, "start_hour": 14, "duration_hours": 1, "location": "Room 4A", "description": "Review Q2 engineering budget.", "attendees": ["sarah", "lisa"]},
    {"summary": "Team Lunch — Offsite", "weekday": 4, "week_offset": 1, "start_hour": 11.5, "duration_hours": 1.5, "location": "Burma Superstar", "description": "Monthly team lunch out."},
    {"summary": "Sprint Demo", "weekday": 4, "week_offset": 1, "start_hour": 14, "duration_hours": 1, "location": "Auditorium", "description": "Demo sprint 23 deliverables.", "attendees": ["sarah", "marcus", "priya", "james", "lisa", "nina"]},
    {"summary": "Yoga Class", "weekday": 5, "week_offset": 1, "start_hour": 8, "duration_hours": 1, "location": "Yoga Studio on Valencia", "description": "Vinyasa flow."},
    {"summary": "Board Game Night", "weekday": 5, "week_offset": 1, "start_hour": 19, "duration_hours": 3, "location": "Marcus's place", "description": "Monthly game night."},
    {"summary": "Long Run — Golden Gate", "weekday": 6, "week_offset": 1, "start_hour": 7, "duration_hours": 1.5, "location": "Crissy Field", "description": "10k training run."},
    {"summary": "Call with Parents", "weekday": 6, "week_offset": 1, "start_hour": 18.5, "duration_hours": 0.5, "location": "", "description": "Weekly family call."},
]


IETF_CORE_INTERIM_CANCEL_EVENT = [
    {
        "summary": "[core] CoRE WG Virtual Interim 2026-02-25",
        "start_date": "2026-02-25",
        "start_hour": 15,
        "duration_hours": 1.5,
        "calendar": "primary",
        "location": "",
        "description": (
            "Dear all,\n"
            "Just a reminder that we have a virtual interim meeting scheduled on Wednesday, February 25 at 15:00-16:30 UTC.\n"
            "The information for the meeting is as follows.\n"
            "- Material: [1]\n"
            "- Meetecho: [2]\n"
            "- Notes: [3]\n"
            "Please go to the notes [3] and add topics you would like to discuss to the agenda.\n"
            "*** If there are no agenda items by 18:00 UTC on Tuesday, the meeting will be cancelled. ***\n"
            "Best,\n"
            "/Marco\n\n"
            "[1]\n"
            "https://datatracker.ietf.org/meeting/interim-2026-core-04/session/core\n"
            "[2]\n"
            "https://meetings.conf.meetecho.com/interim/?group=7e3fae63-ae83-4607-8d84-35f31a3eb39d\n"
            "[3]\n"
            "https://notes.ietf.org/notes-ietf-interim-2026-core-04-core"
        ),
    }
]


_PACKS = {
    "federal_register_meeting_amendments": _pack(
        "federal_register_meeting_amendments",
        needle_events=FEDERAL_REGISTER_MEETING_AMENDMENT_SEED_EVENTS,
    ),
    "fosdem_2023_amendments": _pack(
        "fosdem_2023_amendments",
        needle_events=FOSDEM_2023_AMENDMENT_SEED_EVENTS,
    ),
    "ietf_core_interim_cancel_event": _pack(
        "ietf_core_interim_cancel_event",
        needle_events=IETF_CORE_INTERIM_CANCEL_EVENT,
    ),
    "ietf_interim_cancelled_sessions": _pack(
        "ietf_interim_cancelled_sessions",
        needle_events=IETF_INTERIM_CANCELLED_SESSION_SEED_EVENTS,
    ),
    "multi_mail_cal_sync_actions": _pack(
        "multi_mail_cal_sync_actions",
        needle_events=MULTI_MAIL_CAL_SYNC_ACTION_SEED_EVENTS,
    ),
    "multi_mail_cal_sync_week_layout": _pack(
        "multi_mail_cal_sync_week_layout",
        needle_events=MULTI_MAIL_CAL_SYNC_WEEK_LAYOUT_EVENTS,
    ),
}
