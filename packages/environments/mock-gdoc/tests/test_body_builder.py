"""Tests for body_builder rich-text conversion functions."""

from mock_gdoc.seed.body_builder import (
    body_to_html,
    create_empty_body,
    text_to_body,
)


class TestBodyToHtml:
    def test_empty_body(self):
        body = create_empty_body()
        html = body_to_html(body)
        # Empty body should produce a single empty paragraph
        assert "<p" in html

    def test_plain_text_paragraphs(self):
        body = text_to_body("Hello world\n\nSecond paragraph")
        html = body_to_html(body)
        assert "Hello world" in html
        assert "Second paragraph" in html
        assert html.count("<p") == 2

    def test_bold_text_run(self):
        body = text_to_body("Hello")
        # Manually set bold on the text run
        para = body["content"][1]["paragraph"]
        para["elements"][0]["textRun"]["textStyle"] = {"bold": True}
        html = body_to_html(body)
        assert "<b>" in html or "font-weight" in html

    def test_italic_text_run(self):
        body = text_to_body("Hello")
        para = body["content"][1]["paragraph"]
        para["elements"][0]["textRun"]["textStyle"] = {"italic": True}
        html = body_to_html(body)
        assert "<i>" in html or "font-style" in html

    def test_underline_text_run(self):
        body = text_to_body("Hello")
        para = body["content"][1]["paragraph"]
        para["elements"][0]["textRun"]["textStyle"] = {"underline": True}
        html = body_to_html(body)
        assert "<u>" in html or "text-decoration" in html

    def test_font_family(self):
        body = text_to_body("Hello")
        para = body["content"][1]["paragraph"]
        para["elements"][0]["textRun"]["textStyle"] = {
            "weightedFontFamily": {"fontFamily": "Georgia", "weight": 400}
        }
        html = body_to_html(body)
        assert "Georgia" in html

    def test_font_size(self):
        body = text_to_body("Hello")
        para = body["content"][1]["paragraph"]
        para["elements"][0]["textRun"]["textStyle"] = {
            "fontSize": {"magnitude": 18, "unit": "PT"}
        }
        html = body_to_html(body)
        assert "18pt" in html or "18" in html

    def test_paragraph_alignment_center(self):
        body = text_to_body("Hello")
        para = body["content"][1]["paragraph"]
        para["paragraphStyle"] = {"alignment": "CENTER"}
        html = body_to_html(body)
        assert "text-align" in html
        assert "center" in html

    def test_paragraph_alignment_end(self):
        body = text_to_body("Hello")
        para = body["content"][1]["paragraph"]
        para["paragraphStyle"] = {"alignment": "END"}
        html = body_to_html(body)
        assert "right" in html

    def test_paragraph_alignment_justified(self):
        body = text_to_body("Hello")
        para = body["content"][1]["paragraph"]
        para["paragraphStyle"] = {"alignment": "JUSTIFIED"}
        html = body_to_html(body)
        assert "justify" in html

    def test_line_spacing(self):
        body = text_to_body("Hello")
        para = body["content"][1]["paragraph"]
        para["paragraphStyle"] = {"lineSpacing": 200}
        html = body_to_html(body)
        assert "line-height" in html
        assert "2" in html

    def test_heading_style(self):
        body = text_to_body("Title text")
        para = body["content"][1]["paragraph"]
        para["paragraphStyle"] = {"namedStyleType": "HEADING_1"}
        html = body_to_html(body)
        assert "<h1" in html

    def test_foreground_color(self):
        body = text_to_body("Red text")
        para = body["content"][1]["paragraph"]
        para["elements"][0]["textRun"]["textStyle"] = {
            "foregroundColor": {"color": {"rgbColor": {"red": 1.0, "green": 0, "blue": 0}}}
        }
        html = body_to_html(body)
        assert "color:" in html or "color: " in html

    def test_none_body(self):
        assert body_to_html(None) == ""

    def test_empty_dict(self):
        assert body_to_html({}) == ""


from mock_gdoc.seed.body_builder import html_to_body


class TestHtmlToBody:
    def test_plain_paragraphs(self):
        html = "<p>Hello world</p><p>Second paragraph</p>"
        body = html_to_body(html)
        content = body["content"]
        # First element is sectionBreak, then two paragraphs
        paragraphs = [e for e in content if "paragraph" in e]
        assert len(paragraphs) == 2
        assert paragraphs[0]["paragraph"]["elements"][0]["textRun"]["content"] == "Hello world\n"
        assert paragraphs[1]["paragraph"]["elements"][0]["textRun"]["content"] == "Second paragraph\n"

    def test_bold_tag(self):
        html = "<p><b>Bold text</b></p>"
        body = html_to_body(html)
        para = [e for e in body["content"] if "paragraph" in e][0]
        tr = para["paragraph"]["elements"][0]["textRun"]
        assert tr["textStyle"].get("bold") is True

    def test_italic_tag(self):
        html = "<p><i>Italic text</i></p>"
        body = html_to_body(html)
        para = [e for e in body["content"] if "paragraph" in e][0]
        tr = para["paragraph"]["elements"][0]["textRun"]
        assert tr["textStyle"].get("italic") is True

    def test_underline_tag(self):
        html = "<p><u>Underlined</u></p>"
        body = html_to_body(html)
        para = [e for e in body["content"] if "paragraph" in e][0]
        tr = para["paragraph"]["elements"][0]["textRun"]
        assert tr["textStyle"].get("underline") is True

    def test_font_family_from_span_style(self):
        html = '<p><span style="font-family: Georgia">Fancy</span></p>'
        body = html_to_body(html)
        para = [e for e in body["content"] if "paragraph" in e][0]
        tr = para["paragraph"]["elements"][0]["textRun"]
        assert tr["textStyle"]["weightedFontFamily"]["fontFamily"] == "Georgia"

    def test_font_size_from_span_style(self):
        html = '<p><span style="font-size: 18pt">Big</span></p>'
        body = html_to_body(html)
        para = [e for e in body["content"] if "paragraph" in e][0]
        tr = para["paragraph"]["elements"][0]["textRun"]
        assert tr["textStyle"]["fontSize"]["magnitude"] == 18

    def test_text_align_center(self):
        html = '<p style="text-align: center">Centered</p>'
        body = html_to_body(html)
        para = [e for e in body["content"] if "paragraph" in e][0]
        assert para["paragraph"]["paragraphStyle"]["alignment"] == "CENTER"

    def test_text_align_right(self):
        html = '<p style="text-align: right">Right</p>'
        body = html_to_body(html)
        para = [e for e in body["content"] if "paragraph" in e][0]
        assert para["paragraph"]["paragraphStyle"]["alignment"] == "END"

    def test_text_align_justify(self):
        html = '<p style="text-align: justify">Justified</p>'
        body = html_to_body(html)
        para = [e for e in body["content"] if "paragraph" in e][0]
        assert para["paragraph"]["paragraphStyle"]["alignment"] == "JUSTIFIED"

    def test_heading_h1(self):
        html = "<h1>Title</h1>"
        body = html_to_body(html)
        para = [e for e in body["content"] if "paragraph" in e][0]
        assert para["paragraph"]["paragraphStyle"]["namedStyleType"] == "HEADING_1"

    def test_heading_h2(self):
        html = "<h2>Subtitle</h2>"
        body = html_to_body(html)
        para = [e for e in body["content"] if "paragraph" in e][0]
        assert para["paragraph"]["paragraphStyle"]["namedStyleType"] == "HEADING_2"

    def test_mixed_runs(self):
        html = "<p>Normal <b>bold</b> <i>italic</i></p>"
        body = html_to_body(html)
        para = [e for e in body["content"] if "paragraph" in e][0]
        elements = para["paragraph"]["elements"]
        assert len(elements) >= 3

    def test_empty_html(self):
        body = html_to_body("")
        paragraphs = [e for e in body["content"] if "paragraph" in e]
        assert len(paragraphs) >= 1  # At least one empty paragraph

    def test_div_treated_as_paragraph(self):
        html = "<div>Text in div</div>"
        body = html_to_body(html)
        paragraphs = [e for e in body["content"] if "paragraph" in e]
        assert len(paragraphs) == 1

    def test_line_height_style(self):
        html = '<p style="line-height: 2">Spaced</p>'
        body = html_to_body(html)
        para = [e for e in body["content"] if "paragraph" in e][0]
        assert para["paragraph"]["paragraphStyle"]["lineSpacing"] == 200

    def test_foreground_color(self):
        html = '<p><span style="color: rgb(255, 0, 0)">Red</span></p>'
        body = html_to_body(html)
        para = [e for e in body["content"] if "paragraph" in e][0]
        tr = para["paragraph"]["elements"][0]["textRun"]
        fg = tr["textStyle"]["foregroundColor"]["color"]["rgbColor"]
        assert fg["red"] == 1.0
        assert fg["green"] == 0.0

    def test_roundtrip_preserves_text(self):
        """body_to_html -> html_to_body -> extract_plain_text should preserve text."""
        from mock_gdoc.seed.body_builder import extract_plain_text
        original = text_to_body("First paragraph\n\nSecond paragraph")
        html = body_to_html(original)
        roundtripped = html_to_body(html)
        text = extract_plain_text(roundtripped)
        assert "First paragraph" in text
        assert "Second paragraph" in text

    def test_roundtrip_preserves_bold(self):
        """Bold style survives a roundtrip."""
        original = text_to_body("Bold text")
        para = original["content"][1]["paragraph"]
        para["elements"][0]["textRun"]["textStyle"] = {"bold": True}
        html = body_to_html(original)
        roundtripped = html_to_body(html)
        para_rt = [e for e in roundtripped["content"] if "paragraph" in e][0]
        assert para_rt["paragraph"]["elements"][0]["textRun"]["textStyle"].get("bold") is True

    def test_roundtrip_preserves_alignment(self):
        """Alignment survives a roundtrip."""
        original = text_to_body("Centered")
        original["content"][1]["paragraph"]["paragraphStyle"] = {"alignment": "CENTER"}
        html = body_to_html(original)
        roundtripped = html_to_body(html)
        para_rt = [e for e in roundtripped["content"] if "paragraph" in e][0]
        assert para_rt["paragraph"]["paragraphStyle"]["alignment"] == "CENTER"
