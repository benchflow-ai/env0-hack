"""Conformance tests — verify mock Calendar response shapes match real gws fixtures."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mock_gcal.models import init_db, reset_engine
from mock_gcal.seed.generator import seed_database

@pytest.fixture
def gcal_db_path(tmp_path):
    path = str(tmp_path / "test_gcal_conformance.db")
    yield path
    reset_engine()

@pytest.fixture
def gcal_seeded_db(gcal_db_path):
    reset_engine()
    seed_database(scenario="default", seed=42, db_path=gcal_db_path)
    return gcal_db_path

@pytest.fixture
def gcal_client(gcal_seeded_db):
    reset_engine()
    init_db(gcal_seeded_db)
    from mock_gcal.api.app import app

    with TestClient(app) as client:
        yield client
    reset_engine()

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "real_gcal"


def load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Golden fixture {name} not found")
    data = json.loads(path.read_text())
    data.pop("_captured_at", None)
    return data


def _assert_shape(real, mock, path="", strict=False):
    """Recursively assert mock response shape matches real fixture.

    Checks:
    - Missing keys: real_keys - mock_keys (always)
    - Extra keys: mock_keys - real_keys (when strict=True)
    - Type mismatches at leaf nodes
    """
    if isinstance(real, dict) and isinstance(mock, dict):
        real_keys = set(real.keys())
        mock_keys = set(mock.keys())
        missing = real_keys - mock_keys
        assert not missing, f"Mock MISSING keys at {path or 'root'}: {missing}"
        if strict:
            extra = mock_keys - real_keys
            assert not extra, f"Mock has EXTRA keys at {path or 'root'}: {extra}"
        for key in real_keys & mock_keys:
            _assert_shape(real[key], mock[key], f"{path}.{key}" if path else key, strict)
        return

    if isinstance(real, list) and isinstance(mock, list):
        if real and not mock:
            pytest.fail(f"Mock list is empty at {path or 'root'}, real fixture has items")
        if not real:
            return
        for idx, item in enumerate(mock):
            _assert_any_shape(real, item, f"{path}[{idx}]", strict)
    else:
        if real is not None and mock is not None:
            real_type = type(real).__name__
            mock_type = type(mock).__name__
            assert real_type == mock_type, f"TYPE MISMATCH at {path}: real={real_type}, mock={mock_type}"


def _assert_any_shape(real_items: list, mock_item, path: str, strict: bool) -> None:
    errors = []
    for real_item in real_items:
        try:
            _assert_shape(real_item, mock_item, path, strict)
            return
        except AssertionError as exc:
            errors.append(str(exc))
    pytest.fail(f"Mock item at {path} matches no fixture item shape: {'; '.join(errors)}")


def _assert_top_level_keys_equal(real: dict, mock: dict):
    assert set(real.keys()) == set(mock.keys())


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class TestCalendarReadsConformance:
    def test_calendarlist_list_shape(self, gcal_client):
        real = load_fixture("calendarlist_list.json")
        primary_shape = real["items"][0]
        secondary_shape = load_fixture("calendarlist_get_secondary.json")
        mock = gcal_client.get("/calendar/v3/users/me/calendarList").json()
        _assert_top_level_keys_equal(real, mock)
        for item in mock["items"]:
            shape = primary_shape if item.get("primary") else secondary_shape
            if not item.get("primary") and not item.get("selected"):
                shape = {key: value for key, value in shape.items() if key != "selected"}
            _assert_shape(shape, item, strict=False)

    def test_calendarlist_get_primary_shape(self, gcal_client):
        real = load_fixture("calendarlist_get_primary.json")
        mock = gcal_client.get("/calendar/v3/users/me/calendarList/primary").json()
        _assert_top_level_keys_equal(real, mock)
        _assert_shape(real, mock)

    def test_calendarlist_get_secondary_shape(self, gcal_client):
        created = gcal_client.post(
            "/calendar/v3/calendars",
            json={"summary": "Updated 172946", "description": "Updated desc", "timeZone": "UTC"},
        )
        assert created.status_code == 200
        cal_id = created.json()["id"]

        patched = gcal_client.patch(
            f"/calendar/v3/users/me/calendarList/{cal_id}",
            json={"selected": True, "colorId": "3"},
        )
        assert patched.status_code == 200

        real = load_fixture("calendarlist_get_secondary.json")
        mock = gcal_client.get(f"/calendar/v3/users/me/calendarList/{cal_id}").json()
        _assert_top_level_keys_equal(real, mock)
        _assert_shape(real, mock)

    def test_calendars_get_primary_shape(self, gcal_client):
        real = load_fixture("calendars_get_primary.json")
        mock = gcal_client.get("/calendar/v3/calendars/primary").json()
        _assert_top_level_keys_equal(real, mock)
        _assert_shape(real, mock)

    def test_events_list_shape(self, gcal_client):
        real = load_fixture("events_list_primary.json")
        # Insert an event with all optional fields so the mock response shape
        # matches the enriched real fixture (attendees, location, description).
        start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1)
        end = start + timedelta(hours=1)
        gcal_client.post(
            "/calendar/v3/calendars/primary/events",
            json={
                "summary": "Fixture Shape Event",
                "description": "Fixture test event with all optional fields",
                "location": "Conference Room A",
                "attendees": [{"email": "fixture-user@example.com"}],
                "start": {"dateTime": _rfc3339(start), "timeZone": "UTC"},
                "end": {"dateTime": _rfc3339(end), "timeZone": "UTC"},
            },
        )
        mock = gcal_client.get(
            "/calendar/v3/calendars/primary/events",
            params={
                "maxResults": 5,
                "singleEvents": True,
                "orderBy": "startTime",
                "timeMin": _rfc3339(start - timedelta(minutes=5)),
                "q": "Fixture Shape Event",
            },
        ).json()
        _assert_shape(real, mock, strict=False)

    def test_events_list_secondary_shape(self, gcal_client):
        cal = gcal_client.post(
            "/calendar/v3/calendars",
            json={"summary": "Updated 172946", "description": "Updated desc", "timeZone": "UTC"},
        ).json()
        start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
        end = start + timedelta(hours=1)
        inserted = gcal_client.post(
            f"/calendar/v3/calendars/{cal['id']}/events",
            json={
                "summary": "Fixture Event 172946",
                "description": "Fixture body",
                "location": "Virtual",
                "attendees": [{"email": "fixture-user@example.com"}],
                "start": {"dateTime": _rfc3339(start), "timeZone": "UTC"},
                "end": {"dateTime": _rfc3339(end), "timeZone": "UTC"},
            },
        )
        assert inserted.status_code == 200

        real = load_fixture("events_list_secondary.json")
        mock = gcal_client.get(f"/calendar/v3/calendars/{cal['id']}/events").json()
        _assert_top_level_keys_equal(real, mock)
        _assert_shape(real, mock, strict=False)

    def test_events_get_shape(self, gcal_client):
        real = load_fixture("events_get_primary.json")
        # Insert an event with all optional fields so the mock response matches
        # the enriched real fixture (attendees, location, description, creator.self).
        start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=2)
        end = start + timedelta(hours=1)
        inserted = gcal_client.post(
            "/calendar/v3/calendars/primary/events",
            json={
                "summary": "Fixture Get Event",
                "description": "Fixture test event with all optional fields",
                "location": "Conference Room A",
                "attendees": [{"email": "fixture-user@example.com"}],
                "start": {"dateTime": _rfc3339(start), "timeZone": "UTC"},
                "end": {"dateTime": _rfc3339(end), "timeZone": "UTC"},
            },
        )
        event_id = inserted.json()["id"]
        mock = gcal_client.get(f"/calendar/v3/calendars/primary/events/{event_id}").json()
        _assert_shape(real, mock, strict=False)  # Known gap: EventActor sparse serialization (API_NOTES.md)

    def test_events_get_secondary_shape(self, gcal_client):
        cal = gcal_client.post(
            "/calendar/v3/calendars",
            json={"summary": "Updated 172946", "description": "Updated desc", "timeZone": "UTC"},
        ).json()
        start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
        end = start + timedelta(hours=1)
        inserted = gcal_client.post(
            f"/calendar/v3/calendars/{cal['id']}/events",
            json={
                "summary": "Fixture Event 172946",
                "description": "Fixture body",
                "location": "Virtual",
                "attendees": [{"email": "fixture-user@example.com"}],
                "start": {"dateTime": _rfc3339(start), "timeZone": "UTC"},
                "end": {"dateTime": _rfc3339(end), "timeZone": "UTC"},
            },
        )
        event_id = inserted.json()["id"]

        real = load_fixture("events_get_response.json")
        mock = gcal_client.get(f"/calendar/v3/calendars/{cal['id']}/events/{event_id}").json()
        _assert_top_level_keys_equal(real, mock)
        _assert_shape(real, mock, strict=False)


class TestSettingsAndMetaConformance:
    def test_colors_shape(self, gcal_client):
        real = load_fixture("colors_get.json")
        mock = gcal_client.get("/calendar/v3/colors").json()
        _assert_top_level_keys_equal(real, mock)
        _assert_shape(real, mock)

    def test_settings_list_shape(self, gcal_client):
        real = load_fixture("settings_list.json")
        mock = gcal_client.get("/calendar/v3/users/me/settings").json()
        _assert_top_level_keys_equal(real, mock)
        _assert_shape(real, mock)

    def test_settings_get_shape(self, gcal_client):
        real = load_fixture("settings_get_timezone.json")
        mock = gcal_client.get("/calendar/v3/users/me/settings/timezone").json()
        _assert_top_level_keys_equal(real, mock)
        _assert_shape(real, mock)

    def test_freebusy_shape(self, gcal_client):
        real = load_fixture("freebusy_query_primary.json")
        now = datetime.now(timezone.utc).replace(microsecond=0)
        body = {
            "timeMin": _rfc3339(now - timedelta(days=1)),
            "timeMax": _rfc3339(now + timedelta(days=1)),
            "items": [{"id": "primary"}],
        }
        mock = gcal_client.post("/calendar/v3/freeBusy", json=body).json()
        _assert_top_level_keys_equal(real, mock)
        _assert_shape(real, mock)

    def test_acl_list_shape(self, gcal_client):
        real = load_fixture("acl_list_primary.json")
        mock = gcal_client.get("/calendar/v3/calendars/primary/acl").json()
        _assert_top_level_keys_equal(real, mock)
        _assert_shape(real, mock)


class TestWriteConformance:
    def test_calendars_insert_patch_update_shapes(self, gcal_client):
        real_insert = load_fixture("calendars_insert_response.json")
        real_patch = load_fixture("calendars_patch_response.json")
        real_update = load_fixture("calendars_update_response.json")

        insert = gcal_client.post(
            "/calendar/v3/calendars",
            json={"summary": "Conf Insert", "description": "x", "timeZone": "UTC"},
        )
        assert insert.status_code == 200
        cal = insert.json()
        _assert_top_level_keys_equal(real_insert, cal)
        _assert_shape(real_insert, cal)

        patch = gcal_client.patch(
            f"/calendar/v3/calendars/{cal['id']}",
            json={"summary": "Conf Patch"},
        )
        assert patch.status_code == 200
        _assert_top_level_keys_equal(real_patch, patch.json())
        _assert_shape(real_patch, patch.json())

        update = gcal_client.put(
            f"/calendar/v3/calendars/{cal['id']}",
            json={"summary": "Conf Update", "description": "y", "timeZone": "UTC"},
        )
        assert update.status_code == 200
        _assert_top_level_keys_equal(real_update, update.json())
        _assert_shape(real_update, update.json())

    def test_events_insert_patch_update_shapes(self, gcal_client):
        real_insert = load_fixture("events_insert_response.json")
        real_patch = load_fixture("events_patch_response.json")
        real_update = load_fixture("events_update_response.json")

        cal = gcal_client.post(
            "/calendar/v3/calendars",
            json={"summary": "Event conf", "description": "z", "timeZone": "UTC"},
        ).json()

        start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
        end = start + timedelta(hours=1)

        insert = gcal_client.post(
            f"/calendar/v3/calendars/{cal['id']}/events",
            json={
                "summary": "Conf Event",
                "description": "d",
                "location": "Virtual",
                "attendees": [{"email": "fixture-user@example.com"}],
                "start": {"dateTime": _rfc3339(start), "timeZone": "UTC"},
                "end": {"dateTime": _rfc3339(end), "timeZone": "UTC"},
            },
        )
        assert insert.status_code == 200
        event = insert.json()
        _assert_top_level_keys_equal(real_insert, event)
        _assert_shape(real_insert, event, strict=False)

        patch = gcal_client.patch(
            f"/calendar/v3/calendars/{cal['id']}/events/{event['id']}",
            json={"summary": "Patched"},
        )
        assert patch.status_code == 200
        _assert_top_level_keys_equal(real_patch, patch.json())
        _assert_shape(real_patch, patch.json(), strict=False)

        start2 = start + timedelta(days=1)
        end2 = start2 + timedelta(hours=2)
        update = gcal_client.put(
            f"/calendar/v3/calendars/{cal['id']}/events/{event['id']}",
            json={
                "summary": "Updated",
                "description": "updated",
                "location": "Room B",
                "attendees": [{"email": "fixture-user@example.com"}],
                "start": {"dateTime": _rfc3339(start2), "timeZone": "UTC"},
                "end": {"dateTime": _rfc3339(end2), "timeZone": "UTC"},
            },
        )
        assert update.status_code == 200
        _assert_top_level_keys_equal(real_update, update.json())
        _assert_shape(real_update, update.json(), strict=False)

    def test_events_import_missing_icaluid_error_shape(self, gcal_client):
        real = load_fixture("events_import_response.json")
        cal = gcal_client.post(
            "/calendar/v3/calendars",
            json={"summary": "Import conf", "description": "z", "timeZone": "UTC"},
        ).json()
        start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
        end = start + timedelta(hours=1)

        resp = gcal_client.post(
            f"/calendar/v3/calendars/{cal['id']}/events/import",
            json={
                "summary": "Import without UID",
                "start": {"dateTime": _rfc3339(start), "timeZone": "UTC"},
                "end": {"dateTime": _rfc3339(end), "timeZone": "UTC"},
            },
        )
        assert resp.status_code == 400
        mock = resp.json()
        assert set(real["error"].keys()).issubset(set(mock["error"].keys()))
        assert mock["error"]["message"] == real["error"]["message"]
        assert mock["error"]["reason"] == real["error"]["reason"]

    def test_error_event_not_found_shape(self, gcal_client):
        real = load_fixture("error_event_not_found.json")
        resp = gcal_client.get("/calendar/v3/calendars/primary/events/nonexistent_event_id_12345")
        assert resp.status_code == 404
        mock = resp.json()
        assert "error" in mock
        assert set(real["error"].keys()).issubset(set(mock["error"].keys()))
        assert mock["error"]["code"] == 404

    def test_error_calendar_not_found_shape(self, gcal_client):
        real = load_fixture("error_calendar_not_found.json")
        resp = gcal_client.get("/calendar/v3/calendars/nonexistent_calendar_id_12345")
        assert resp.status_code == 404
        mock = resp.json()
        assert "error" in mock
        assert set(real["error"].keys()).issubset(set(mock["error"].keys()))
        assert mock["error"]["code"] == 404

    def test_error_invalid_event_shape(self, gcal_client):
        """Real API returns 400 for missing start/end. Mock now converts
        Pydantic 422 to Google-style 400 via RequestValidationError handler.
        """
        real = load_fixture("error_invalid_event.json")
        resp = gcal_client.post(
            "/calendar/v3/calendars/primary/events",
            json={"summary": "Missing start/end"},
        )
        assert resp.status_code == 400
        mock = resp.json()
        assert "error" in mock
        assert set(real["error"].keys()).issubset(set(mock["error"].keys()))
        assert mock["error"]["code"] == 400

    def test_acl_insert_patch_update_get_shapes(self, gcal_client):
        real_insert = load_fixture("acl_insert_response.json")
        real_get = load_fixture("acl_get_response.json")
        real_patch = load_fixture("acl_patch_response.json")
        real_update = load_fixture("acl_update_response.json")

        insert = gcal_client.post(
            "/calendar/v3/calendars/primary/acl",
            json={"role": "reader", "scope": {"type": "user", "value": "fixture-user@example.com"}},
        )
        assert insert.status_code == 200
        rule = insert.json()
        _assert_top_level_keys_equal(real_insert, rule)
        _assert_shape(real_insert, rule)

        get = gcal_client.get(f"/calendar/v3/calendars/primary/acl/{rule['id']}")
        assert get.status_code == 200
        _assert_top_level_keys_equal(real_get, get.json())
        _assert_shape(real_get, get.json())

        patch = gcal_client.patch(
            f"/calendar/v3/calendars/primary/acl/{rule['id']}",
            json={"role": "writer"},
        )
        assert patch.status_code == 200
        _assert_top_level_keys_equal(real_patch, patch.json())
        _assert_shape(real_patch, patch.json())

        update = gcal_client.put(
            f"/calendar/v3/calendars/primary/acl/{rule['id']}",
            json={"role": "reader", "scope": {"type": "user", "value": "fixture-user@example.com"}},
        )
        assert update.status_code == 200
        _assert_top_level_keys_equal(real_update, update.json())
        _assert_shape(real_update, update.json(), strict=False)

    def test_events_watch_shape(self, gcal_client):
        real = load_fixture("events_watch_response.json")
        mock = gcal_client.post(
            "/calendar/v3/calendars/primary/events/watch",
            json={"id": "conformance-watch", "type": "web_hook", "address": "https://example.com/hook"},
        ).json()
        _assert_top_level_keys_equal(real, mock)
        _assert_shape(real, mock)

    def test_events_move_shape(self, gcal_client):
        real = load_fixture("events_move_response.json")
        cal = gcal_client.post(
            "/calendar/v3/calendars",
            json={"summary": "Move Fixture", "description": "Updated desc", "timeZone": "UTC"},
        ).json()
        start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
        end = start + timedelta(hours=1)
        inserted = gcal_client.post(
            f"/calendar/v3/calendars/{cal['id']}/events",
            json={
                "summary": "Fixture Move Event",
                "description": "Fixture test event with all optional fields",
                "location": "Conference Room A",
                "attendees": [{"email": "fixture-user@example.com"}],
                "start": {"dateTime": _rfc3339(start), "timeZone": "UTC"},
                "end": {"dateTime": _rfc3339(end), "timeZone": "UTC"},
            },
        )
        event_id = inserted.json()["id"]

        mock = gcal_client.post(
            f"/calendar/v3/calendars/{cal['id']}/events/{event_id}/move",
            params={"destination": "primary"},
        ).json()
        _assert_top_level_keys_equal(real, mock)
        _assert_shape(real, mock, strict=False)

    def test_events_quickadd_shape(self, gcal_client):
        real = load_fixture("events_quickadd_response.json")
        cal = gcal_client.post(
            "/calendar/v3/calendars",
            json={"summary": "QuickAdd Fixture", "description": "Updated desc", "timeZone": "UTC"},
        ).json()
        mock = gcal_client.post(
            f"/calendar/v3/calendars/{cal['id']}/events/quickAdd",
            params={"text": "Lunch tomorrow noon"},
        ).json()
        _assert_top_level_keys_equal(real, mock)
        _assert_shape(real, mock, strict=False)  # Known gap: EventActor sparse serialization (API_NOTES.md)

    def test_events_instances_shape(self, gcal_client):
        real = load_fixture("events_instances_response.json")
        cal = gcal_client.post(
            "/calendar/v3/calendars",
            json={"summary": "Updated 172946", "description": "Updated desc", "timeZone": "UTC"},
        ).json()
        start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
        end = start + timedelta(hours=1)
        inserted = gcal_client.post(
            f"/calendar/v3/calendars/{cal['id']}/events",
            json={
                "summary": "Fixture Event 172946",
                "description": "Fixture body",
                "location": "Virtual",
                "attendees": [{"email": "fixture-user@example.com"}],
                "start": {"dateTime": _rfc3339(start), "timeZone": "UTC"},
                "end": {"dateTime": _rfc3339(end), "timeZone": "UTC"},
                "recurrence": ["RRULE:FREQ=DAILY;COUNT=1"],
            },
        )
        event_id = inserted.json()["id"]

        mock = gcal_client.get(f"/calendar/v3/calendars/{cal['id']}/events/{event_id}/instances").json()
        _assert_top_level_keys_equal(real, mock)
        _assert_shape(real, mock, strict=False)
