"""Tests for Revisions API endpoints."""

import json
import pytest
from mock_gdrive.models import Revision


@pytest.fixture()
def seed_revision(db_session, seed_user, seed_file):
    """Create a test revision."""
    rev = Revision(
        id="rev_1",
        file_id=seed_file.id,
        last_modifying_user_id=seed_user.id,
        mime_type="application/vnd.google-apps.document",
        size=1024,
        md5_checksum="abc123",
    )
    db_session.add(rev)
    db_session.commit()
    return rev


class TestRevisionsList:
    def test_list_revisions(self, client, seed_user, seed_file, seed_revision):
        resp = client.get(f"/drive/v3/files/{seed_file.id}/revisions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kind"] == "drive#revisionList"
        assert len(data["revisions"]) == 1
        assert data["revisions"][0]["id"] == "rev_1"

    def test_list_empty(self, client, seed_user, seed_file):
        resp = client.get(f"/drive/v3/files/{seed_file.id}/revisions")
        assert resp.status_code == 200
        assert resp.json()["revisions"] == []


class TestRevisionsGet:
    def test_get_revision(self, client, seed_user, seed_file, seed_revision):
        resp = client.get(f"/drive/v3/files/{seed_file.id}/revisions/rev_1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kind"] == "drive#revision"
        assert data["id"] == "rev_1"
        assert data["size"] == "1024"
        assert data["md5Checksum"] == "abc123"

    def test_get_not_found(self, client, seed_user, seed_file):
        resp = client.get(f"/drive/v3/files/{seed_file.id}/revisions/nonexistent")
        assert resp.status_code == 404


class TestRevisionsUpdate:
    def test_update_keep_forever(self, client, seed_user, seed_file, seed_revision):
        resp = client.patch(
            f"/drive/v3/files/{seed_file.id}/revisions/rev_1",
            content=json.dumps({"keepForever": True}),
        )
        assert resp.status_code == 200
        assert resp.json()["keepForever"] is True


class TestRevisionsDelete:
    def test_delete_revision(self, client, seed_user, seed_file, seed_revision):
        resp = client.delete(f"/drive/v3/files/{seed_file.id}/revisions/rev_1")
        assert resp.status_code == 204

    def test_delete_not_found(self, client, seed_user, seed_file):
        resp = client.delete(f"/drive/v3/files/{seed_file.id}/revisions/nonexistent")
        assert resp.status_code == 404
