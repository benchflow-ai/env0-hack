"""Integration tests for rich content via batchUpdate API."""

import pytest
from starlette.testclient import TestClient

from mock_gdoc.api.app import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        # Reset DB
        c.post("/_admin/reset")
        yield c


def _create_doc(client, title="Test Doc") -> str:
    resp = client.post("/v1/documents", json={"title": title})
    assert resp.status_code == 200
    return resp.json()["documentId"]


def _batch(client, doc_id, requests):
    resp = client.post(
        f"/v1/documents/{doc_id}:batchUpdate",
        json={"requests": requests},
    )
    assert resp.status_code == 200
    return resp.json()


def _get(client, doc_id):
    resp = client.get(f"/v1/documents/{doc_id}")
    assert resp.status_code == 200
    return resp.json()


class TestUpdateTextStyle:
    def test_bold_text(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Hello World\n"}},
            {"updateTextStyle": {
                "range": {"startIndex": 1, "endIndex": 6},
                "textStyle": {"bold": True},
                "fields": "bold",
            }},
        ])
        doc = _get(client, doc_id)
        para = doc["body"]["content"][1]["paragraph"]
        # Should have split into bold "Hello" and non-bold " World\n"
        elements = para["elements"]
        bold_found = False
        for e in elements:
            if "textRun" in e and e["textRun"].get("textStyle", {}).get("bold"):
                assert "Hello" in e["textRun"]["content"]
                bold_found = True
        assert bold_found

    def test_multiple_styles(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Styled text\n"}},
            {"updateTextStyle": {
                "range": {"startIndex": 1, "endIndex": 7},
                "textStyle": {
                    "bold": True,
                    "italic": True,
                    "fontSize": {"magnitude": 18, "unit": "PT"},
                },
                "fields": "bold,italic,fontSize",
            }},
        ])
        doc = _get(client, doc_id)
        para = doc["body"]["content"][1]["paragraph"]
        styled = [e for e in para["elements"]
                  if "textRun" in e and e["textRun"].get("textStyle", {}).get("bold")]
        assert len(styled) >= 1
        ts = styled[0]["textRun"]["textStyle"]
        assert ts["italic"] is True
        assert ts["fontSize"]["magnitude"] == 18


class TestUpdateParagraphStyle:
    def test_heading(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "My Heading\n"}},
            {"updateParagraphStyle": {
                "range": {"startIndex": 1, "endIndex": 12},
                "paragraphStyle": {"namedStyleType": "HEADING_1"},
                "fields": "namedStyleType",
            }},
        ])
        doc = _get(client, doc_id)
        para = doc["body"]["content"][1]["paragraph"]
        assert para["paragraphStyle"]["namedStyleType"] == "HEADING_1"

    def test_alignment(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Centered\n"}},
            {"updateParagraphStyle": {
                "range": {"startIndex": 1, "endIndex": 10},
                "paragraphStyle": {"alignment": "CENTER"},
                "fields": "alignment",
            }},
        ])
        doc = _get(client, doc_id)
        para = doc["body"]["content"][1]["paragraph"]
        assert para["paragraphStyle"]["alignment"] == "CENTER"


class TestLists:
    def test_create_bullets(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Item 1\nItem 2\n"}},
            {"createParagraphBullets": {
                "range": {"startIndex": 1, "endIndex": 15},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }},
        ])
        doc = _get(client, doc_id)
        assert "lists" in doc
        assert len(doc["lists"]) == 1

    def test_numbered_list(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Step 1\nStep 2\n"}},
            {"createParagraphBullets": {
                "range": {"startIndex": 1, "endIndex": 15},
                "bulletPreset": "NUMBERED_DECIMAL_ALPHA_ROMAN",
            }},
        ])
        doc = _get(client, doc_id)
        assert "lists" in doc
        list_id = list(doc["lists"].keys())[0]
        levels = doc["lists"][list_id]["listProperties"]["nestingLevels"]
        assert levels[0]["glyphType"] == "DECIMAL"

    def test_delete_bullets(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Item\n"}},
            {"createParagraphBullets": {
                "range": {"startIndex": 1, "endIndex": 6},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }},
            {"deleteParagraphBullets": {
                "range": {"startIndex": 1, "endIndex": 6},
            }},
        ])
        doc = _get(client, doc_id)
        # Lists map should be empty (orphaned list cleaned up)
        assert "lists" not in doc or len(doc.get("lists", {})) == 0


class TestTables:
    def test_insert_table(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"insertTable": {
                "location": {"index": 1},
                "rows": 2,
                "columns": 3,
            }},
        ])
        doc = _get(client, doc_id)
        tables = [e for e in doc["body"]["content"] if "table" in e]
        assert len(tables) == 1
        assert tables[0]["table"]["rows"] == 2
        assert tables[0]["table"]["columns"] == 3

    def test_insert_text_in_table_cell(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"insertTable": {"location": {"index": 1}, "rows": 1, "columns": 1}},
        ])
        doc = _get(client, doc_id)
        # Find the first cell's paragraph start index
        table = [e for e in doc["body"]["content"] if "table" in e][0]["table"]
        cell = table["tableRows"][0]["tableCells"][0]
        cell_para = cell["content"][0]["paragraph"]
        cell_start = cell["content"][0]["startIndex"]

        # Insert text in the cell
        _batch(client, doc_id, [
            {"insertText": {"location": {"index": cell_start}, "text": "Cell content"}},
        ])
        doc = _get(client, doc_id)
        table = [e for e in doc["body"]["content"] if "table" in e][0]["table"]
        cell = table["tableRows"][0]["tableCells"][0]
        text = ""
        for ce in cell["content"]:
            if "paragraph" in ce:
                for pe in ce["paragraph"]["elements"]:
                    if "textRun" in pe:
                        text += pe["textRun"]["content"]
        assert "Cell content" in text


class TestInlineImages:
    def test_insert_inline_image(self, client):
        doc_id = _create_doc(client)
        result = _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Before image\n"}},
            {"insertInlineImage": {
                "location": {"index": 1},
                "uri": "https://example.com/test.png",
                "objectSize": {
                    "width": {"magnitude": 100, "unit": "PT"},
                    "height": {"magnitude": 75, "unit": "PT"},
                },
            }},
        ])
        # Should return objectId in reply
        assert "insertInlineImage" in result["replies"][1]
        obj_id = result["replies"][1]["insertInlineImage"]["objectId"]

        doc = _get(client, doc_id)
        assert "inlineObjects" in doc
        assert obj_id in doc["inlineObjects"]


class TestPageBreaks:
    def test_insert_page_break(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Page 1\nPage 2\n"}},
            {"insertPageBreak": {"location": {"index": 7}}},
        ])
        doc = _get(client, doc_id)
        # Find page break element
        found = False
        for elem in doc["body"]["content"]:
            if "paragraph" in elem:
                for pe in elem["paragraph"]["elements"]:
                    if "pageBreak" in pe:
                        found = True
        assert found


class TestSectionBreaks:
    def test_insert_section_break(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Section 1\nSection 2\n"}},
            {"insertSectionBreak": {
                "location": {"index": 10},
                "sectionType": "NEXT_PAGE",
            }},
        ])
        doc = _get(client, doc_id)
        sbs = [e for e in doc["body"]["content"] if "sectionBreak" in e]
        assert len(sbs) >= 2


class TestHeadersFooters:
    def test_create_header(self, client):
        doc_id = _create_doc(client)
        result = _batch(client, doc_id, [
            {"createHeader": {"type": "DEFAULT"}},
        ])
        assert "createHeader" in result["replies"][0]
        header_id = result["replies"][0]["createHeader"]["headerId"]

        doc = _get(client, doc_id)
        assert "headers" in doc
        assert header_id in doc["headers"]

    def test_create_and_delete_footer(self, client):
        doc_id = _create_doc(client)
        result = _batch(client, doc_id, [
            {"createFooter": {"type": "DEFAULT"}},
        ])
        footer_id = result["replies"][0]["createFooter"]["footerId"]

        doc = _get(client, doc_id)
        assert footer_id in doc["footers"]

        _batch(client, doc_id, [
            {"deleteFooter": {"footerId": footer_id}},
        ])
        doc = _get(client, doc_id)
        assert "footers" not in doc


class TestFootnotes:
    def test_create_footnote(self, client):
        doc_id = _create_doc(client)
        result = _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Text with note\n"}},
            {"createFootnote": {"location": {"index": 5}}},
        ])
        assert "createFootnote" in result["replies"][1]
        fn_id = result["replies"][1]["createFootnote"]["footnoteId"]

        doc = _get(client, doc_id)
        assert "footnotes" in doc
        assert fn_id in doc["footnotes"]


class TestNamedRanges:
    def test_create_and_delete(self, client):
        doc_id = _create_doc(client)
        result = _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Important text\n"}},
            {"createNamedRange": {
                "name": "important",
                "range": {"startIndex": 1, "endIndex": 10},
            }},
        ])
        assert "createNamedRange" in result["replies"][1]

        doc = _get(client, doc_id)
        assert "namedRanges" in doc

        _batch(client, doc_id, [
            {"deleteNamedRange": {"name": "important"}},
        ])
        doc = _get(client, doc_id)
        assert "namedRanges" not in doc


class TestDocumentStyle:
    def test_update_document_style(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"updateDocumentStyle": {
                "documentStyle": {
                    "marginTop": {"magnitude": 100, "unit": "PT"},
                },
                "fields": "marginTop",
            }},
        ])
        doc = _get(client, doc_id)
        assert doc["documentStyle"]["marginTop"]["magnitude"] == 100

    def test_document_has_default_styles(self, client):
        doc_id = _create_doc(client)
        doc = _get(client, doc_id)
        assert "documentStyle" in doc
        assert "namedStyles" in doc
        assert doc["documentStyle"]["pageSize"]["width"]["magnitude"] == 612
        styles = doc["namedStyles"]["styles"]
        style_types = {s["namedStyleType"] for s in styles}
        assert "NORMAL_TEXT" in style_types
        assert "HEADING_1" in style_types
        assert "TITLE" in style_types


class TestDeletePositionedObject:
    def test_delete_positioned_object(self, client):
        doc_id = _create_doc(client)
        # First insert text, then use body_ops directly to add a positioned object
        _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Hello\n"}},
        ])
        # Use insertInlineImage to set up, then use the positioned object path
        # We need to use body_ops directly to insert a positioned object for setup
        from mock_gdoc.models import get_session_factory, Document
        from mock_gdoc import body_ops
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            doc = db.get(Document, doc_id)
            new_body, new_po, obj_id = body_ops.insert_positioned_object(
                doc.body, doc.positioned_objects, 1,
                "https://example.com/float.png", None, "WRAP_TEXT",
            )
            doc.body = new_body
            doc.positioned_objects = new_po
            db.commit()
        finally:
            db.close()

        doc_data = _get(client, doc_id)
        assert obj_id in doc_data["positionedObjects"]

        # Now delete it via API (deletePositionedObject is a real API request type)
        _batch(client, doc_id, [
            {"deletePositionedObject": {"objectId": obj_id}},
        ])
        doc_data = _get(client, doc_id)
        assert "positionedObjects" not in doc_data


class TestReplaceImage:
    def test_replace_inline_image(self, client):
        doc_id = _create_doc(client)
        result = _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Hello\n"}},
            {"insertInlineImage": {
                "location": {"index": 1},
                "uri": "https://example.com/old.png",
            }},
        ])
        obj_id = result["replies"][1]["insertInlineImage"]["objectId"]

        _batch(client, doc_id, [
            {"replaceImage": {
                "imageObjectId": obj_id,
                "uri": "https://example.com/new.png",
            }},
        ])
        doc = _get(client, doc_id)
        eo = doc["inlineObjects"][obj_id]["inlineObjectProperties"]["embeddedObject"]
        assert eo["imageProperties"]["contentUri"] == "https://example.com/new.png"


class TestReplaceNamedRangeContent:
    def test_replace_named_range(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Hello World Foo\n"}},
            {"createNamedRange": {
                "name": "greeting",
                "range": {"startIndex": 1, "endIndex": 6},
            }},
        ])
        _batch(client, doc_id, [
            {"replaceNamedRangeContent": {
                "namedRangeName": "greeting",
                "text": "Goodbye",
            }},
        ])
        doc = _get(client, doc_id)
        text = ""
        for elem in doc["body"]["content"]:
            if "paragraph" in elem:
                for pe in elem["paragraph"]["elements"]:
                    if "textRun" in pe:
                        text += pe["textRun"]["content"]
        assert "Goodbye" in text


class TestUpdateSectionStyle:
    def test_update_section_style(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"updateSectionStyle": {
                "range": {"startIndex": 0, "endIndex": 2},
                "sectionStyle": {"columnSeparatorStyle": "BETWEEN_EACH_COLUMN"},
                "fields": "columnSeparatorStyle",
            }},
        ])
        doc = _get(client, doc_id)
        sb = doc["body"]["content"][0]["sectionBreak"]["sectionStyle"]
        assert sb["columnSeparatorStyle"] == "BETWEEN_EACH_COLUMN"


class TestPinTableHeaderRows:
    def test_pin_header_rows(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"insertTable": {"location": {"index": 1}, "rows": 3, "columns": 2}},
        ])
        doc = _get(client, doc_id)
        table_elem = [e for e in doc["body"]["content"] if "table" in e][0]
        table_start = table_elem["startIndex"]

        _batch(client, doc_id, [
            {"pinTableHeaderRows": {
                "tableStartLocation": {"index": table_start},
                "pinnedHeaderRowsCount": 1,
            }},
        ])
        doc = _get(client, doc_id)
        table = [e for e in doc["body"]["content"] if "table" in e][0]["table"]
        assert table["tableStyle"]["pinnedHeaderRowsCount"] == 1


class TestTabs:
    def test_add_and_delete_tab(self, client):
        doc_id = _create_doc(client)
        result = _batch(client, doc_id, [
            {"addDocumentTab": {"tabProperties": {"title": "My Tab"}}},
        ])
        assert "addDocumentTab" in result["replies"][0]
        tab_id = result["replies"][0]["addDocumentTab"]["tabId"]

        _batch(client, doc_id, [
            {"deleteTab": {"tabId": tab_id}},
        ])

    def test_update_tab_properties(self, client):
        doc_id = _create_doc(client)
        result = _batch(client, doc_id, [
            {"addDocumentTab": {"tabProperties": {"title": "Old Title"}}},
        ])
        tab_id = result["replies"][0]["addDocumentTab"]["tabId"]

        _batch(client, doc_id, [
            {"updateDocumentTabProperties": {
                "tabProperties": {"tabId": tab_id, "title": "New Title"},
                "fields": "title",
            }},
        ])


class TestInsertPerson:
    def test_insert_person_mention(self, client):
        doc_id = _create_doc(client)
        _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "Assigned to \n"}},
            {"insertPerson": {
                "location": {"index": 13},
                "personProperties": {"email": "alice@example.com", "name": "Alice"},
            }},
        ])
        doc = _get(client, doc_id)
        para = doc["body"]["content"][1]["paragraph"]
        persons = [pe for pe in para["elements"] if "person" in pe]
        assert len(persons) == 1
        assert persons[0]["person"]["personProperties"]["email"] == "alice@example.com"


class TestBatchUpdateResponse:
    def test_write_control_in_response(self, client):
        doc_id = _create_doc(client)
        result = _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "test\n"}},
        ])
        assert "writeControl" in result
        assert "requiredRevisionId" in result["writeControl"]

    def test_multiple_replies(self, client):
        doc_id = _create_doc(client)
        result = _batch(client, doc_id, [
            {"insertText": {"location": {"index": 1}, "text": "hello world\n"}},
            {"replaceAllText": {
                "containsText": {"text": "hello"},
                "replaceText": "goodbye",
            }},
        ])
        assert len(result["replies"]) == 2
        assert result["replies"][1]["replaceAllText"]["occurrencesChanged"] == 1
