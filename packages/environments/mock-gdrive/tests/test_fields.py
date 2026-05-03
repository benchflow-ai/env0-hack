"""Tests for the fields parameter parser and filter."""

from mock_gdrive.api.fields import parse_fields, filter_response


class TestParseFields:
    def test_simple(self):
        result = parse_fields("id,name,mimeType")
        assert result == {"id": {}, "name": {}, "mimeType": {}}

    def test_nested(self):
        result = parse_fields("files(id,name),nextPageToken")
        assert result == {"files": {"id": {}, "name": {}}, "nextPageToken": {}}

    def test_empty(self):
        assert parse_fields("") == {}
        assert parse_fields(None) == {}

    def test_single_field(self):
        assert parse_fields("id") == {"id": {}}

    def test_nested_with_spaces(self):
        result = parse_fields("files( id , name ), nextPageToken")
        assert "files" in result
        assert "id" in result["files"]


class TestFilterResponse:
    def test_filter_top_level(self):
        data = {"id": "123", "name": "test", "mimeType": "text/plain", "size": "100"}
        spec = {"id": {}, "name": {}}
        result = filter_response(data, spec)
        assert result == {"id": "123", "name": "test"}

    def test_filter_nested(self):
        data = {
            "files": [
                {"id": "1", "name": "a", "mimeType": "text/plain"},
                {"id": "2", "name": "b", "mimeType": "text/html"},
            ],
            "nextPageToken": "abc",
        }
        spec = {"files": {"id": {}, "name": {}}, "nextPageToken": {}}
        result = filter_response(data, spec)
        assert result == {
            "files": [{"id": "1", "name": "a"}, {"id": "2", "name": "b"}],
            "nextPageToken": "abc",
        }

    def test_no_filter(self):
        data = {"id": "1", "name": "test"}
        assert filter_response(data, {}) == data

    def test_missing_field(self):
        data = {"id": "1"}
        spec = {"id": {}, "name": {}}
        result = filter_response(data, spec)
        assert result == {"id": "1"}  # name not in data, not included


class TestFilesListDefaultFields:
    """Test that files.list returns minimal fields by default (matching real API)."""

    def test_list_default_returns_minimal_fields(self, client, seed_user, seed_file):
        """Without fields parameter, files.list returns only id, name, mimeType, kind."""
        resp = client.get("/drive/v3/files")
        data = resp.json()
        assert len(data["files"]) > 0
        for f in data["files"]:
            assert set(f.keys()) == {"kind", "id", "name", "mimeType"}, \
                f"Default list should return only kind,id,name,mimeType but got: {set(f.keys())}"

    def test_list_with_fields_returns_requested(self, client, seed_user, seed_file):
        """With fields parameter, files.list returns the requested fields."""
        resp = client.get("/drive/v3/files", params={
            "fields": "files(id,name,parents,owners),nextPageToken"
        })
        data = resp.json()
        f = data["files"][0]
        assert "id" in f
        assert "name" in f
        assert "parents" in f
        assert "owners" in f
        # Non-requested fields should be absent
        assert "capabilities" not in f

    def test_get_returns_full_resource(self, client, seed_user, seed_file):
        """files.get without fields returns full resource (unlike files.list)."""
        resp = client.get(f"/drive/v3/files/{seed_file.id}")
        data = resp.json()
        # Should have many fields including capabilities, owners, etc.
        assert "capabilities" in data
        assert "owners" in data
        assert "createdTime" in data
        assert "modifiedTime" in data
