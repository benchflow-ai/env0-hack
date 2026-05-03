"""Tests for state snapshot serialization — specifically that Filter objects are included."""

import pytest

from mock_gmail.state.snapshots import get_state_dump


class TestFilterSerialization:
    """Verify that filters created via the API appear in the state dump."""

    def test_filters_key_present_when_empty(self, client):
        state = get_state_dump()
        for user_data in state["users"].values():
            assert "filters" in user_data, (
                "_serialize_user must include 'filters' key even when no filters exist"
            )
            assert user_data["filters"] == []

    def test_filter_appears_in_state_dump_after_creation(self, client):
        resp = client.post("/gmail/v1/users/me/settings/filters", json={
            "criteria": {"from": "@newsletter.com"},
            "action": {"addLabelIds": ["INBOX"], "removeLabelIds": ["INBOX"]},
        })
        assert resp.status_code == 201
        filter_id = resp.json()["id"]

        state = get_state_dump()
        all_filters = []
        for user_data in state["users"].values():
            all_filters.extend(user_data.get("filters", []))

        assert len(all_filters) == 1, (
            "Expected 1 filter in state dump after creation, got 0. "
            "_serialize_user does not serialize Filter objects."
        )
        assert all_filters[0]["id"] == filter_id

    def test_filter_criteria_and_action_serialized(self, client):
        client.post("/gmail/v1/users/me/settings/filters", json={
            "criteria": {"from": "@newsletter.com", "subject": "weekly"},
            "action": {"addLabelIds": ["Label_123"], "removeLabelIds": ["INBOX"]},
        })

        state = get_state_dump()
        filters = []
        for user_data in state["users"].values():
            filters.extend(user_data.get("filters", []))

        assert filters, "No filters in state dump"
        f = filters[0]
        assert "criteria" in f
        assert "action" in f
        assert "newsletter.com" in (f["criteria"].get("from") or "")
        assert "Label_123" in f["action"].get("addLabelIds", [])
        assert "INBOX" in f["action"].get("removeLabelIds", [])

    def test_deleted_filter_removed_from_state_dump(self, client):
        resp = client.post("/gmail/v1/users/me/settings/filters", json={
            "criteria": {"from": "@newsletter.com"},
            "action": {},
        })
        filter_id = resp.json()["id"]
        client.delete(f"/gmail/v1/users/me/settings/filters/{filter_id}")

        state = get_state_dump()
        all_filters = []
        for user_data in state["users"].values():
            all_filters.extend(user_data.get("filters", []))

        assert all_filters == [], "Deleted filter should not appear in state dump"
