"""API endpoint tests for mock-gdoc."""

import pytest


class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestDocuments:
    def test_create_document(self, client):
        resp = client.post("/v1/documents", json={"title": "Test Document"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test Document"
        assert "documentId" in data
        assert data["body"] is not None

    def test_get_document(self, client):
        # Create then get
        create_resp = client.post("/v1/documents", json={"title": "Get Test"})
        doc_id = create_resp.json()["documentId"]

        resp = client.get(f"/v1/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Get Test"

    def test_get_document_not_found(self, client):
        resp = client.get("/v1/documents/nonexistent")
        assert resp.status_code == 404

    def test_batch_update_insert_text(self, client):
        create_resp = client.post("/v1/documents", json={"title": "Insert Test"})
        doc_id = create_resp.json()["documentId"]

        resp = client.post(f"/v1/documents/{doc_id}:batchUpdate", json={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1},
                        "text": "Hello, World!",
                    }
                }
            ]
        })
        assert resp.status_code == 200
        assert resp.json()["documentId"] == doc_id

        # Verify content
        doc = client.get(f"/v1/documents/{doc_id}").json()
        body_text = _extract_text(doc["body"])
        assert "Hello, World!" in body_text

    def test_batch_update_replace_all_text(self, client):
        # Create doc with content
        create_resp = client.post("/v1/documents", json={"title": "Replace Test"})
        doc_id = create_resp.json()["documentId"]

        # Insert initial text
        client.post(f"/v1/documents/{doc_id}:batchUpdate", json={
            "requests": [{"insertText": {"location": {"index": 1}, "text": "foo bar foo"}}]
        })

        # Replace all "foo" with "baz"
        resp = client.post(f"/v1/documents/{doc_id}:batchUpdate", json={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {"text": "foo", "matchCase": True},
                        "replaceText": "baz",
                    }
                }
            ]
        })
        assert resp.status_code == 200
        reply = resp.json()["replies"][0]
        assert reply["replaceAllText"]["occurrencesChanged"] == 2

        # Verify content
        doc = client.get(f"/v1/documents/{doc_id}").json()
        body_text = _extract_text(doc["body"])
        assert "baz bar baz" in body_text
        assert "foo" not in body_text


class TestAdmin:
    def test_state_dump(self, client):
        resp = client.get("/_admin/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "users" in data
        # Check documents exist
        for user_data in data["users"].values():
            assert "documents" in user_data

    def test_diff_no_changes(self, client):
        resp = client.get("/_admin/diff")
        assert resp.status_code == 200
        data = resp.json()
        # No changes yet
        assert data.get("updated", {}) == {} or all(
            not any(v.get("documents", {}).values())
            for v in data.get("updated", {}).values()
        )

    def test_diff_after_create(self, client):
        client.post("/v1/documents", json={"title": "Diff Test"})
        resp = client.get("/_admin/diff")
        assert resp.status_code == 200
        data = resp.json()
        # Should show added document
        has_added = False
        for user_data in data.get("updated", {}).values():
            if user_data.get("documents", {}).get("added"):
                has_added = True
        assert has_added

    def test_action_log(self, client):
        client.post("/v1/documents", json={"title": "Log Test"})
        resp = client.get("/_admin/action_log")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] > 0
        assert len(data["entries"]) > 0

    def test_reset(self, client):
        # Create a document
        create_resp = client.post("/v1/documents", json={"title": "Will Be Gone"})
        doc_id = create_resp.json()["documentId"]

        # Reset
        resp = client.post("/_admin/reset")
        assert resp.status_code == 200

        # Verify the new document is gone
        resp = client.get(f"/v1/documents/{doc_id}")
        assert resp.status_code == 404


def _extract_text(body: dict) -> str:
    """Helper to extract plain text from body structure."""
    text_parts = []
    for element in body.get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for para_element in paragraph.get("elements", []):
            text_run = para_element.get("textRun")
            if text_run:
                text_parts.append(text_run.get("content", ""))
    return "".join(text_parts)
