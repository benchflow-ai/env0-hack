"""Tests for the About API endpoint."""


class TestAbout:
    def test_get_about(self, client, seed_user):
        resp = client.get("/drive/v3/about")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kind"] == "drive#about"
        assert data["user"]["emailAddress"] == "test@example.com"
        assert data["user"]["me"] is True
        assert "storageQuota" in data

    def test_about_fields(self, client, seed_user):
        resp = client.get("/drive/v3/about", params={"fields": "user"})
        assert resp.status_code == 200
        data = resp.json()
        assert "user" in data
        assert "storageQuota" not in data
