"""Tests for Changes API endpoints."""

import json
import pytest
from mock_gdrive.models import Change


class TestChangesStartPageToken:
    def test_get_start_page_token(self, client, seed_user):
        resp = client.get("/drive/v3/changes/startPageToken")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kind"] == "drive#startPageToken"
        assert "startPageToken" in data


class TestChangesList:
    def test_list_changes_empty(self, client, seed_user):
        resp = client.get("/drive/v3/changes", params={"pageToken": "1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["kind"] == "drive#changeList"
        assert data["changes"] == []

    def test_list_changes_after_create(self, client, seed_user, seed_folder):
        # Create a file (should record a change)
        resp = client.post(
            "/drive/v3/files",
            content=json.dumps({
                "name": "change-test.txt",
                "mimeType": "text/plain",
                "parents": [seed_folder.id],
            }),
        )
        assert resp.status_code == 200

        # Get start token
        token_resp = client.get("/drive/v3/changes/startPageToken")
        # Changes should have been recorded, get from token 1
        changes_resp = client.get("/drive/v3/changes", params={"pageToken": "1"})
        data = changes_resp.json()
        assert len(data["changes"]) >= 1
        change = data["changes"][0]
        assert change["changeType"] == "file"

    def test_requires_page_token(self, client, seed_user):
        resp = client.get("/drive/v3/changes")
        assert resp.status_code == 400  # Missing required param (Google-style error)


class TestChangesWatch:
    def test_watch_changes(self, client, seed_user):
        resp = client.post("/drive/v3/changes/watch", params={"pageToken": "1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["kind"] == "api#channel"


class TestChannelsStop:
    def test_stop_channel(self, client):
        resp = client.post("/drive/v3/channels/stop")
        assert resp.status_code == 200
