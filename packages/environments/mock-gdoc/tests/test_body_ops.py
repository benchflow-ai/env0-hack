"""Unit tests for the body_ops engine."""

import pytest
from mock_gdoc.body_ops import (
    reindex_body,
    compute_body_length,
    extract_plain_text,
    insert_text,
    delete_range,
    replace_all_text,
    apply_text_style,
    apply_paragraph_style,
    create_paragraph_bullets,
    delete_paragraph_bullets,
    insert_table,
    insert_table_row,
    insert_table_column,
    delete_table_row,
    delete_table_column,
    merge_table_cells,
    insert_page_break,
    insert_section_break,
    insert_inline_image,
    create_header,
    create_footer,
    delete_header,
    create_footnote,
    create_named_range,
    delete_named_range,
    insert_equation,
    insert_table_of_contents,
    insert_positioned_object,
    find_paragraphs_in_range,
)
from mock_gdoc.seed.body_builder import create_empty_body, text_to_body


class TestReindex:
    def test_empty_body(self):
        body = create_empty_body()
        result = reindex_body(body)
        assert result["content"][0]["endIndex"] == 1  # sectionBreak
        assert result["content"][1]["startIndex"] == 1
        assert result["content"][1]["endIndex"] == 2

    def test_reindex_preserves_content(self):
        body = text_to_body("Hello world\n")
        result = reindex_body(body)
        text = extract_plain_text(result)
        assert "Hello world" in text

    def test_compute_body_length(self):
        body = create_empty_body()
        assert compute_body_length(body) == 2

    def test_compute_body_length_with_text(self):
        body = text_to_body("Hello\n")
        assert compute_body_length(body) == 7  # 1 (section) + 6 ("Hello\n")


class TestInsertText:
    def test_insert_at_start(self):
        body = create_empty_body()
        result = insert_text(body, 1, "Hello")
        text = extract_plain_text(result)
        assert "Hello" in text

    def test_insert_preserves_indices(self):
        body = text_to_body("World\n")
        result = insert_text(body, 1, "Hello ")
        text = extract_plain_text(result)
        assert "Hello World" in text
        # Check indices are consistent
        for elem in result["content"]:
            if "paragraph" in elem:
                assert elem["startIndex"] < elem["endIndex"]

    def test_insert_in_middle(self):
        body = text_to_body("Helo\n")
        result = insert_text(body, 3, "l")
        text = extract_plain_text(result)
        assert "Hello" in text


class TestDeleteRange:
    def test_delete_partial(self):
        body = text_to_body("Hello World\n")
        result = delete_range(body, 6, 12)
        text = extract_plain_text(result)
        assert text.strip() == "Hello"

    def test_delete_preserves_section_break(self):
        body = text_to_body("Test\n")
        result = delete_range(body, 1, 100)
        # Should still have section break and at least one paragraph
        assert any("sectionBreak" in e for e in result["content"])
        assert any("paragraph" in e for e in result["content"])


class TestReplaceAllText:
    def test_replace_basic(self):
        body = text_to_body("Hello World\n")
        result, count = replace_all_text(body, "World", "Earth")
        assert count == 1
        text = extract_plain_text(result)
        assert "Earth" in text
        assert "World" not in text

    def test_replace_case_insensitive(self):
        body = text_to_body("Hello WORLD\n")
        result, count = replace_all_text(body, "world", "Earth", match_case=False)
        assert count == 1
        text = extract_plain_text(result)
        assert "Earth" in text

    def test_replace_multiple(self):
        body = text_to_body("cat and cat and cat\n")
        result, count = replace_all_text(body, "cat", "dog")
        assert count == 3
        text = extract_plain_text(result)
        assert text.count("dog") == 3

    def test_replace_no_match(self):
        body = text_to_body("Hello\n")
        result, count = replace_all_text(body, "xyz", "abc")
        assert count == 0


class TestApplyTextStyle:
    def test_apply_bold(self):
        body = text_to_body("Hello World\n")
        result = apply_text_style(body, 1, 6, {"bold": True}, "bold")
        # Find the text run containing "Hello"
        para = result["content"][1]["paragraph"]
        bold_runs = [
            pe for pe in para["elements"]
            if "textRun" in pe and pe["textRun"].get("textStyle", {}).get("bold")
        ]
        assert len(bold_runs) >= 1
        assert "Hello" in bold_runs[0]["textRun"]["content"]

    def test_apply_font_size(self):
        body = text_to_body("Test\n")
        style = {"fontSize": {"magnitude": 20, "unit": "PT"}}
        result = apply_text_style(body, 1, 5, style, "fontSize")
        para = result["content"][1]["paragraph"]
        for pe in para["elements"]:
            if "textRun" in pe and "Test" in pe["textRun"]["content"]:
                assert pe["textRun"]["textStyle"]["fontSize"]["magnitude"] == 20

    def test_style_splits_text_runs(self):
        body = text_to_body("Hello World\n")
        # Bold only "Hello" (indices 1-6)
        result = apply_text_style(body, 1, 6, {"bold": True}, "bold")
        para = result["content"][1]["paragraph"]
        # Should have at least 2 text runs (bold "Hello" + non-bold " World\n")
        text_runs = [pe for pe in para["elements"] if "textRun" in pe]
        assert len(text_runs) >= 2


class TestApplyParagraphStyle:
    def test_apply_heading(self):
        body = text_to_body("Title\n")
        result = apply_paragraph_style(
            body, 1, 7, {"namedStyleType": "HEADING_1"}, "namedStyleType"
        )
        para = result["content"][1]["paragraph"]
        assert para["paragraphStyle"]["namedStyleType"] == "HEADING_1"

    def test_apply_alignment(self):
        body = text_to_body("Centered\n")
        result = apply_paragraph_style(
            body, 1, 10, {"alignment": "CENTER"}, "alignment"
        )
        para = result["content"][1]["paragraph"]
        assert para["paragraphStyle"]["alignment"] == "CENTER"


class TestLists:
    def test_create_bullets(self):
        body = text_to_body("Item 1\nItem 2\nItem 3\n")
        lists = {}
        new_body, new_lists = create_paragraph_bullets(
            body, lists, 1, 25, "BULLET_DISC_CIRCLE_SQUARE"
        )
        # Should have created a list entry
        assert len(new_lists) == 1
        list_id = list(new_lists.keys())[0]
        assert list_id.startswith("kix.")

        # Paragraphs should have bullet
        paragraphs = find_paragraphs_in_range(new_body, 1, 25)
        for p in paragraphs:
            assert "bullet" in p["paragraph"]
            assert p["paragraph"]["bullet"]["listId"] == list_id

    def test_delete_bullets(self):
        body = text_to_body("Item 1\n")
        lists = {}
        new_body, new_lists = create_paragraph_bullets(
            body, lists, 1, 10, "NUMBERED_DECIMAL_ALPHA_ROMAN"
        )
        assert len(new_lists) == 1

        new_body2, new_lists2 = delete_paragraph_bullets(new_body, new_lists, 1, 10)
        # Bullet should be removed
        para = new_body2["content"][1]["paragraph"]
        assert "bullet" not in para
        # Orphaned list should be cleaned up
        assert len(new_lists2) == 0


class TestTables:
    def test_insert_table(self):
        body = create_empty_body()
        result = insert_table(body, 1, 2, 3)
        # Should have a table element
        tables = [e for e in result["content"] if "table" in e]
        assert len(tables) == 1
        table = tables[0]["table"]
        assert table["rows"] == 2
        assert table["columns"] == 3
        assert len(table["tableRows"]) == 2
        assert len(table["tableRows"][0]["tableCells"]) == 3

    def test_table_indices_consistent(self):
        body = create_empty_body()
        result = insert_table(body, 1, 2, 2)
        # All indices should be monotonically increasing
        prev_end = 0
        for elem in result["content"]:
            if "sectionBreak" in elem:
                assert elem["endIndex"] > prev_end
                prev_end = elem["endIndex"]
            elif "table" in elem:
                assert elem["startIndex"] >= prev_end
                assert elem["endIndex"] > elem["startIndex"]
                prev_end = elem["endIndex"]
            elif "paragraph" in elem:
                assert elem["startIndex"] >= prev_end
                assert elem["endIndex"] > elem["startIndex"]
                prev_end = elem["endIndex"]

    def test_insert_table_row(self):
        body = create_empty_body()
        body = insert_table(body, 1, 2, 2)
        table_elem = [e for e in body["content"] if "table" in e][0]
        table_start = table_elem["startIndex"]

        result = insert_table_row(body, table_start, 0, True)
        table = [e for e in result["content"] if "table" in e][0]["table"]
        assert table["rows"] == 3

    def test_insert_table_column(self):
        body = create_empty_body()
        body = insert_table(body, 1, 2, 2)
        table_elem = [e for e in body["content"] if "table" in e][0]
        table_start = table_elem["startIndex"]

        result = insert_table_column(body, table_start, 0, True)
        table = [e for e in result["content"] if "table" in e][0]["table"]
        assert table["columns"] == 3

    def test_delete_table_row(self):
        body = create_empty_body()
        body = insert_table(body, 1, 3, 2)
        table_elem = [e for e in body["content"] if "table" in e][0]
        table_start = table_elem["startIndex"]

        result = delete_table_row(body, table_start, 1)
        table = [e for e in result["content"] if "table" in e][0]["table"]
        assert table["rows"] == 2

    def test_delete_table_column(self):
        body = create_empty_body()
        body = insert_table(body, 1, 2, 3)
        table_elem = [e for e in body["content"] if "table" in e][0]
        table_start = table_elem["startIndex"]

        result = delete_table_column(body, table_start, 1)
        table = [e for e in result["content"] if "table" in e][0]["table"]
        assert table["columns"] == 2

    def test_merge_cells(self):
        body = create_empty_body()
        body = insert_table(body, 1, 2, 2)
        table_elem = [e for e in body["content"] if "table" in e][0]
        table_start = table_elem["startIndex"]

        result = merge_table_cells(body, table_start, 0, 0, 2, 1)
        table = [e for e in result["content"] if "table" in e][0]["table"]
        anchor = table["tableRows"][0]["tableCells"][0]
        assert anchor["tableCellStyle"]["rowSpan"] == 2


class TestPageAndSectionBreaks:
    def test_insert_page_break(self):
        body = text_to_body("Hello World\n")
        result = insert_page_break(body, 6)
        para = result["content"][1]["paragraph"]
        page_breaks = [pe for pe in para["elements"] if "pageBreak" in pe]
        assert len(page_breaks) == 1

    def test_insert_section_break(self):
        body = text_to_body("Before\nAfter\n")
        result = insert_section_break(body, 8, "NEXT_PAGE")
        section_breaks = [e for e in result["content"] if "sectionBreak" in e]
        assert len(section_breaks) >= 2  # Original + new


class TestInlineImages:
    def test_insert_inline_image(self):
        body = text_to_body("Hello\n")
        inline_objects = {}
        new_body, new_io, obj_id = insert_inline_image(
            body, inline_objects, 1, "https://example.com/img.png"
        )
        assert obj_id.startswith("kix.")
        assert obj_id in new_io
        assert new_io[obj_id]["inlineObjectProperties"]["embeddedObject"]["imageProperties"]["contentUri"] == "https://example.com/img.png"

        # Should have an inlineObjectElement in the paragraph
        para = new_body["content"][1]["paragraph"]
        ioe = [pe for pe in para["elements"] if "inlineObjectElement" in pe]
        assert len(ioe) == 1
        assert ioe[0]["inlineObjectElement"]["inlineObjectId"] == obj_id


class TestHeadersFooters:
    def test_create_header(self):
        body = create_empty_body()
        headers = {}
        new_body, new_headers, hid = create_header(body, headers)
        assert hid.startswith("kix.")
        assert hid in new_headers
        assert new_headers[hid]["content"]

        # Section break should reference the header
        sb = new_body["content"][0]["sectionBreak"]["sectionStyle"]
        assert sb["defaultHeaderId"] == hid

    def test_create_footer(self):
        body = create_empty_body()
        footers = {}
        new_body, new_footers, fid = create_footer(body, footers)
        assert fid in new_footers
        sb = new_body["content"][0]["sectionBreak"]["sectionStyle"]
        assert sb["defaultFooterId"] == fid

    def test_delete_header(self):
        body = create_empty_body()
        headers = {}
        new_body, new_headers, hid = create_header(body, headers)
        new_body2, new_headers2 = delete_header(new_body, new_headers, hid)
        assert hid not in new_headers2
        sb = new_body2["content"][0]["sectionBreak"]["sectionStyle"]
        assert "defaultHeaderId" not in sb


class TestFootnotes:
    def test_create_footnote(self):
        body = text_to_body("Hello World\n")
        footnotes = {}
        new_body, new_fn, fn_id = create_footnote(body, footnotes, 6)
        assert fn_id.startswith("kix.")
        assert fn_id in new_fn
        assert new_fn[fn_id]["content"]

        # Should have a footnoteReference in the paragraph
        para = new_body["content"][1]["paragraph"]
        refs = [pe for pe in para["elements"] if "footnoteReference" in pe]
        assert len(refs) == 1
        assert refs[0]["footnoteReference"]["footnoteId"] == fn_id


class TestNamedRanges:
    def test_create_named_range(self):
        nr = {}
        new_nr, rid = create_named_range(nr, "my_range", 5, 15)
        assert "my_range" in new_nr
        assert rid.startswith("kix.")

    def test_delete_named_range_by_name(self):
        nr = {}
        new_nr, _ = create_named_range(nr, "my_range", 5, 15)
        result = delete_named_range(new_nr, name="my_range")
        assert "my_range" not in result


class TestEquations:
    def test_insert_equation(self):
        body = text_to_body("Hello\n")
        result = insert_equation(body, 1)
        para = result["content"][1]["paragraph"]
        eqs = [pe for pe in para["elements"] if "equation" in pe]
        assert len(eqs) == 1


class TestTableOfContents:
    def test_insert_toc(self):
        # Create body with headings
        body = text_to_body("Title\n\nSection 1\n\nContent\n")
        body = apply_paragraph_style(body, 1, 7, {"namedStyleType": "HEADING_1"}, "namedStyleType")
        length = compute_body_length(body)
        result = insert_table_of_contents(body, length - 1)
        tocs = [e for e in result["content"] if "tableOfContents" in e]
        assert len(tocs) == 1


class TestPositionedObjects:
    def test_insert_positioned_object(self):
        body = text_to_body("Hello\n")
        po = {}
        new_body, new_po, obj_id = insert_positioned_object(
            body, po, 1, "https://example.com/float.png"
        )
        assert obj_id in new_po
        para = new_body["content"][1]["paragraph"]
        assert obj_id in para.get("positionedObjectIds", [])
