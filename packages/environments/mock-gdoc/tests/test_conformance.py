"""Conformance tests — verify mock response shapes match real Google API golden fixtures.

Tests check key presence/absence and structural properties against captured fixtures.
Golden fixtures live in tests/fixtures/real_gdocs/ (captured via scripts/capture_fixtures.py).

Organized by resource, following mock-gcal pattern with _assert_shape() recursive helper.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "real_gdocs"


def load_fixture(name: str) -> dict | None:
    """Load a golden fixture file, stripping capture metadata.

    Returns None if fixture doesn't exist yet (allows tests to skip gracefully).
    """
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Golden fixture {name} not found")
    data = json.loads(path.read_text())
    data.pop("_captured_at", None)
    return data


def _assert_shape(real, mock, path: str = "", strict=True):
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
            _assert_shape(real[key], mock[key], path=f"{path}.{key}" if path else key, strict=strict)
        return

    if isinstance(real, list) and isinstance(mock, list):
        if real and not mock:
            pytest.fail(f"Mock list is empty at {path or 'root'}, real fixture has items")
        if not real:
            return
        for idx, item in enumerate(mock):
            _assert_any_shape(real, item, path=f"{path}[{idx}]", strict=strict)
    else:
        if real is not None and mock is not None:
            real_type = type(real).__name__
            mock_type = type(mock).__name__
            assert real_type == mock_type, f"TYPE MISMATCH at {path}: real={real_type}, mock={mock_type}"


def _assert_any_shape(real_items: list, mock_item, path: str, strict: bool) -> None:
    errors = []
    for real_item in real_items:
        try:
            _assert_shape(real_item, mock_item, path=path, strict=strict)
            return
        except AssertionError as exc:
            errors.append(str(exc))
    pytest.fail(f"Mock item at {path} matches no fixture item shape: {'; '.join(errors)}")


def _assert_top_level_keys_equal(real: dict, mock: dict, skip_keys: set[str] | None = None):
    """Assert that mock has exactly the same top-level keys as real (minus skip_keys)."""
    real_keys = set(real.keys())
    mock_keys = set(mock.keys())
    if skip_keys:
        real_keys -= skip_keys
        mock_keys -= skip_keys
    assert real_keys == mock_keys, (
        f"Key mismatch — extra in mock: {mock_keys - real_keys}, "
        f"missing in mock: {real_keys - mock_keys}"
    )


# --- Documents API conformance ---


class TestDocumentsConformance:
    """Verify Docs API response shapes match real Google Docs API."""

    # Expected keys from real API golden fixture (document_get.json)
    DOCUMENT_REQUIRED_KEYS = {"documentId", "title", "body", "revisionId", "suggestionsViewMode", "documentStyle", "namedStyles"}

    def test_get_document_keys(self, client):
        """documents.get shape should match golden fixture."""
        real = load_fixture("document_get.json")
        create_resp = client.post("/v1/documents", json={"title": "Conformance Test"})
        doc_id = create_resp.json()["documentId"]

        resp = client.get(f"/v1/documents/{doc_id}")
        assert resp.status_code == 200
        mock = resp.json()

        # Required keys must be present
        missing = self.DOCUMENT_REQUIRED_KEYS - set(mock.keys())
        assert not missing, f"Missing required keys: {missing}"

        # Compare against golden fixture (skip tabs — intentionally not implemented)
        if real:
            _assert_top_level_keys_equal(real, mock, skip_keys={"tabs"})

    def test_get_document_body_structure(self, client):
        """Document body should have content[] starting with sectionBreak, matching real API."""
        create_resp = client.post("/v1/documents", json={"title": "Body Test"})
        doc_id = create_resp.json()["documentId"]

        # Insert some text so body is non-trivial
        client.post(f"/v1/documents/{doc_id}:batchUpdate", json={
            "requests": [{"insertText": {"location": {"index": 1}, "text": "Hello World\nSecond line"}}]
        })

        resp = client.get(f"/v1/documents/{doc_id}")
        body = resp.json()["body"]

        assert "content" in body
        assert isinstance(body["content"], list)
        assert len(body["content"]) > 0

        # Real API: first element is always a sectionBreak
        first = body["content"][0]
        assert "sectionBreak" in first, "First content element must be a sectionBreak (matches real API)"
        section_style = first["sectionBreak"]["sectionStyle"]
        assert section_style["sectionType"] == "CONTINUOUS"
        assert section_style["contentDirection"] == "LEFT_TO_RIGHT"

        # Each content element should be a structural element
        for element in body["content"]:
            assert isinstance(element, dict)
            has_structure = any(
                k in element for k in ("paragraph", "sectionBreak", "table")
            )
            assert has_structure, f"Element has no structural type: {element.keys()}"

        # Check paragraph → elements → textRun nesting
        paragraphs = [e for e in body["content"] if e.get("paragraph")]
        assert len(paragraphs) > 0, "No paragraphs found in body"

        for para in paragraphs:
            p = para["paragraph"]
            assert "elements" in p
            assert "paragraphStyle" in p
            assert p["paragraphStyle"].get("direction") == "LEFT_TO_RIGHT"
            for pe in p["elements"]:
                if pe.get("textRun"):
                    tr = pe["textRun"]
                    assert "content" in tr

    def test_get_document_body_shape_vs_fixture(self, client):
        """Document body.content structure should match golden fixture shape recursively."""
        real = load_fixture("document_get.json")
        create_resp = client.post("/v1/documents", json={"title": "Shape Test"})
        doc_id = create_resp.json()["documentId"]

        # Insert text to make body non-trivial
        client.post(f"/v1/documents/{doc_id}:batchUpdate", json={
            "requests": [{"insertText": {"location": {"index": 1}, "text": "test content"}}]
        })

        resp = client.get(f"/v1/documents/{doc_id}")
        mock = resp.json()

        if real:
            # Compare body structure recursively
            _assert_shape(real["body"], mock["body"], path="body")

    def test_create_document_keys(self, client):
        """documents.create should return a full Document resource matching fixture."""
        real = load_fixture("document_create.json")
        resp = client.post("/v1/documents", json={"title": "Create Conformance"})
        assert resp.status_code == 200
        mock = resp.json()

        # Create returns full document (unlike Gmail mutations)
        missing = self.DOCUMENT_REQUIRED_KEYS - set(mock.keys())
        assert not missing, f"Missing required keys in create response: {missing}"
        assert mock["title"] == "Create Conformance"

        # Compare against fixture (skip tabs)
        if real:
            _assert_top_level_keys_equal(real, mock, skip_keys={"tabs"})

    def test_batch_update_response_keys(self, client):
        """batchUpdate should return {documentId, replies[], writeControl} matching fixture."""
        real = load_fixture("document_batch_update.json")
        create_resp = client.post("/v1/documents", json={"title": "BatchUpdate Conformance"})
        doc_id = create_resp.json()["documentId"]

        resp = client.post(f"/v1/documents/{doc_id}:batchUpdate", json={
            "requests": [{"insertText": {"location": {"index": 1}, "text": "test"}}]
        })
        assert resp.status_code == 200
        mock = resp.json()

        assert "documentId" in mock
        assert "replies" in mock
        assert "writeControl" in mock, "batchUpdate must return writeControl (matches real API)"
        assert isinstance(mock["replies"], list)
        assert mock["documentId"] == doc_id
        assert "requiredRevisionId" in mock["writeControl"]

        # Compare against golden fixture
        if real:
            _assert_top_level_keys_equal(real, mock)
            _assert_shape(real, mock)

    def test_batch_update_replace_reply_shape(self, client):
        """replaceAllText reply shape should match golden fixture."""
        real = load_fixture("document_batch_update_replace.json")
        create_resp = client.post("/v1/documents", json={"title": "Replace Conformance"})
        doc_id = create_resp.json()["documentId"]

        # Insert text first
        client.post(f"/v1/documents/{doc_id}:batchUpdate", json={
            "requests": [{"insertText": {"location": {"index": 1}, "text": "aaa bbb aaa"}}]
        })

        # Replace
        resp = client.post(f"/v1/documents/{doc_id}:batchUpdate", json={
            "requests": [{
                "replaceAllText": {
                    "containsText": {"text": "aaa", "matchCase": True},
                    "replaceText": "ccc",
                }
            }]
        })
        mock = resp.json()
        reply = mock["replies"][0]

        assert "replaceAllText" in reply
        assert "occurrencesChanged" in reply["replaceAllText"]
        assert reply["replaceAllText"]["occurrencesChanged"] == 2

        # Compare against golden fixture
        if real:
            _assert_top_level_keys_equal(real, mock)

    def test_error_response_google_format(self, client):
        """404 should return Google API error format."""
        resp = client.get("/v1/documents/nonexistent_id_12345")
        assert resp.status_code == 404
        data = resp.json()

        assert "error" in data
        err = data["error"]
        assert "code" in err
        assert "message" in err
        assert "status" in err
        assert err["code"] == 404
        assert err["status"] == "NOT_FOUND"


# --- Admin endpoints conformance ---


class TestAdminConformance:
    """Verify admin endpoints return expected structure."""

    def test_state_dump_structure(self, client):
        """_admin/state should return {users: {id: {user, documents, comments, revisions}}}."""
        resp = client.get("/_admin/state")
        assert resp.status_code == 200
        data = resp.json()

        assert "users" in data
        assert "timestamp" in data

        for user_id, user_data in data["users"].items():
            assert "user" in user_data
            assert "documents" in user_data
            assert "comments" in user_data
            assert "revisions" in user_data

            u = user_data["user"]
            assert "id" in u
            assert "email" in u
            assert "displayName" in u

    def test_diff_structure(self, client):
        """_admin/diff should return {added, updated, deleted}."""
        resp = client.get("/_admin/diff")
        assert resp.status_code == 200
        data = resp.json()

        assert "added" in data
        assert "updated" in data
        assert "deleted" in data

    def test_action_log_structure(self, client):
        """_admin/action_log should return {entries[], count}."""
        # Make a request first
        client.post("/v1/documents", json={"title": "Log Test"})

        resp = client.get("/_admin/action_log")
        assert resp.status_code == 200
        data = resp.json()

        assert "entries" in data
        assert "count" in data
        assert isinstance(data["entries"], list)
        assert data["count"] == len(data["entries"])


class TestErrorConformance:
    """Verify error response shapes match real Google API error envelope."""

    def test_document_not_found_error(self, client):
        real = load_fixture("document_not_found_error.json")
        if real is None:
            pytest.skip("No fixture")
        resp = client.get("/v1/documents/nonexistent_doc_id_12345")
        assert resp.status_code == 404
        mock = resp.json()
        assert "error" in mock
        assert set(real["error"].keys()).issubset(set(mock["error"].keys()))
        assert mock["error"]["code"] == 404

    def test_file_not_found_error(self, client):
        """Drive API 404 — used by GDocs capture to verify doc existence."""
        real = load_fixture("file_not_found_error.json")
        if real is None:
            pytest.skip("No fixture")
        # This fixture is from Drive API, not Docs API. Verify envelope shape only.
        assert "error" in real
        assert real["error"]["code"] == 404
        assert "message" in real["error"]


class TestDriveFixturesConformance:
    """Drive API fixtures captured alongside Docs for document discovery.

    These test the fixture shapes are valid, not the Docs mock — the Docs
    mock does not serve Drive endpoints. These fixtures exist because the
    capture script uses Drive to find/list documents.
    """

    def test_drive_files_list_shape(self):
        real = load_fixture("drive_files_list.json")
        if real is None:
            pytest.skip("No fixture")
        assert "files" in real
        assert isinstance(real["files"], list)
        if real["files"]:
            assert "id" in real["files"][0]
            assert "name" in real["files"][0]

    def test_drive_files_list_empty_shape(self):
        real = load_fixture("drive_files_list_empty.json")
        if real is None:
            pytest.skip("No fixture")
        assert "files" in real
        assert real["files"] == []
        assert real.get("kind") == "drive#fileList"

    def test_drive_files_get_shape(self):
        real = load_fixture("drive_files_get.json")
        if real is None:
            pytest.skip("No fixture")
        assert "id" in real
        assert "name" in real
        assert "mimeType" in real
        assert real.get("kind") == "drive#file"
