"""Direct tests for mock-gdoc web route functions."""

from __future__ import annotations


def test_dashboard_renders_html(client):
    response = client.get("/dev/dashboard")
    assert response.status_code == 200
    html = response.text
    assert "mock-gdoc Dashboard" in html
    assert "Documents" in html


def test_api_explorer_lists_document_endpoint(client):
    response = client.get("/dev/api-explorer")
    assert response.status_code == 200
    html = response.text
    assert "/v1/documents" in html
    assert "batchUpdate" in html


def test_dev_tasks_route_removed(client):
    response = client.get("/dev/tasks")
    assert response.status_code == 404


def test_doc_list_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "Docs" in html
    assert "My Drive" in html
    assert "/dev/tasks" not in html


def test_doc_editor_renders(client):
    response = client.get("/")
    html = response.text
    import re
    links = re.findall(r'href="/doc/([^"]+)"', html)
    if links:
        doc_response = client.get(f"/doc/{links[0]}")
        assert doc_response.status_code == 200
        assert "Share" in doc_response.text
        assert 'id="share-button"' in doc_response.text
        assert 'id="share-dialog"' in doc_response.text
        assert 'id="comments-toggle-btn"' in doc_response.text
        assert 'id="comment-dialog"' in doc_response.text
        assert 'id="comments-panel"' in doc_response.text
        assert 'contenteditable="true"' in doc_response.text
        assert "katex" in doc_response.text


def test_doc_save(client):
    response = client.get("/")
    import re
    links = re.findall(r'href="/doc/([^"]+)"', response.text)
    assert links, "Expected at least one document"
    doc_id = links[0]

    save_resp = client.post(
        f"/doc/{doc_id}/save",
        json={"content": "Hello world\n\nSecond paragraph"},
    )
    assert save_resp.status_code == 200
    assert save_resp.json()["status"] == "ok"

    doc_resp = client.get(f"/doc/{doc_id}")
    assert "Hello world" in doc_resp.text
    assert "Second paragraph" in doc_resp.text


def test_doc_save_not_found(client):
    resp = client.post("/doc/nonexistent123/save", json={"content": "test"})
    assert resp.status_code == 404


def test_doc_save_html(client):
    """Save with format=html should preserve formatting in body JSON."""
    import re
    response = client.get("/")
    links = re.findall(r'href="/doc/([^"]+)"', response.text)
    assert links
    doc_id = links[0]

    html_content = '<p style="text-align: center"><b>Bold centered</b></p><p>Normal text</p>'
    save_resp = client.post(
        f"/doc/{doc_id}/save",
        json={"content": html_content, "format": "html"},
    )
    assert save_resp.status_code == 200
    assert save_resp.json()["status"] == "ok"

    # Verify the body JSON has the formatting
    api_resp = client.get(f"/v1/documents/{doc_id}", headers={"X-Mock-Gdoc-User": "test"})
    body = api_resp.json()["body"]
    paragraphs = [e for e in body["content"] if "paragraph" in e]
    assert len(paragraphs) == 2
    # First paragraph should be centered with bold
    assert paragraphs[0]["paragraph"]["paragraphStyle"].get("alignment") == "CENTER"
    assert paragraphs[0]["paragraph"]["elements"][0]["textRun"]["textStyle"].get("bold") is True
