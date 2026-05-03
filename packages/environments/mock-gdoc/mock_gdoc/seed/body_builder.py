"""Utilities to convert plain text to Google Docs body JSON structure."""

from __future__ import annotations

import html as html_mod
import re


_SECTION_BREAK = {
    "endIndex": 1,
    "sectionBreak": {
        "sectionStyle": {
            "columnSeparatorStyle": "NONE",
            "contentDirection": "LEFT_TO_RIGHT",
            "sectionType": "CONTINUOUS",
        }
    },
}


def create_empty_body() -> dict:
    """Return the body structure for a new blank document.

    Matches real Google Docs API: starts with a sectionBreak at index 0-1,
    followed by a single empty paragraph "\n" at index 1-2.
    """
    return {
        "content": [
            _SECTION_BREAK,
            {
                "startIndex": 1,
                "endIndex": 2,
                "paragraph": {
                    "elements": [
                        {
                            "startIndex": 1,
                            "endIndex": 2,
                            "textRun": {
                                "content": "\n",
                                "textStyle": {},
                            },
                        }
                    ],
                    "paragraphStyle": {
                        "namedStyleType": "NORMAL_TEXT",
                        "direction": "LEFT_TO_RIGHT",
                    },
                },
            }
        ]
    }


def text_to_body(text: str) -> dict:
    """Convert plain text to a Google Docs body JSON structure.

    Splits on double newlines for paragraph breaks. Single newlines
    become line breaks within a paragraph.
    """
    if not text or not text.strip():
        return create_empty_body()

    # Ensure text ends with a newline (Google Docs always does)
    if not text.endswith("\n"):
        text = text + "\n"

    paragraphs = text.split("\n\n")
    elements = [_SECTION_BREAK]  # Real API always starts with sectionBreak
    index = 1  # Google Docs body indices start at 1

    for i, para_text in enumerate(paragraphs):
        if not para_text and i < len(paragraphs) - 1:
            # Empty paragraph between double newlines
            para_text = "\n"
        elif not para_text:
            continue

        # Ensure paragraph ends with newline
        if not para_text.endswith("\n"):
            para_text = para_text + "\n"

        # Add the extra newline for paragraph separation (except first)
        if i > 0:
            para_text = "\n" + para_text

        end_index = index + len(para_text)

        paragraph_element = {
            "startIndex": index,
            "endIndex": end_index,
            "paragraph": {
                "elements": [
                    {
                        "startIndex": index,
                        "endIndex": end_index,
                        "textRun": {
                            "content": para_text,
                            "textStyle": {},
                        },
                    }
                ],
                "paragraphStyle": {
                    "namedStyleType": "NORMAL_TEXT",
                    "direction": "LEFT_TO_RIGHT",
                },
            },
        }

        elements.append(paragraph_element)
        index = end_index

    if not elements:
        return create_empty_body()

    return {"content": elements}


def extract_plain_text(body: dict) -> str:
    """Extract plain text from a Google Docs body JSON structure."""
    if not body:
        return ""

    text_parts: list[str] = []
    _extract_text_from_elements(body.get("content", []), text_parts)
    return "".join(text_parts)


def _extract_text_from_elements(elements: list[dict], parts: list[str]):
    for element in elements:
        if "paragraph" in element and element["paragraph"]:
            for para_element in element["paragraph"].get("elements", []):
                text_run = para_element.get("textRun")
                if text_run:
                    parts.append(text_run.get("content", ""))
        elif "table" in element and element["table"]:
            for row in element["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    _extract_text_from_elements(cell.get("content", []), parts)
        elif "tableOfContents" in element and element["tableOfContents"]:
            _extract_text_from_elements(
                element["tableOfContents"].get("content", []), parts
            )


def create_default_document_style() -> dict:
    """Return the default documentStyle matching the real Google Docs API."""
    return {
        "background": {"color": {}},
        "pageNumberStart": 1,
        "marginTop": {"magnitude": 72, "unit": "PT"},
        "marginBottom": {"magnitude": 72, "unit": "PT"},
        "marginRight": {"magnitude": 72, "unit": "PT"},
        "marginLeft": {"magnitude": 72, "unit": "PT"},
        "pageSize": {
            "height": {"magnitude": 792, "unit": "PT"},
            "width": {"magnitude": 612, "unit": "PT"},
        },
        "marginHeader": {"magnitude": 36, "unit": "PT"},
        "marginFooter": {"magnitude": 36, "unit": "PT"},
        "useCustomHeaderFooterMargins": True,
        "documentFormat": {"documentMode": "PAGES"},
    }


def create_default_named_styles() -> dict:
    """Return the default namedStyles matching the real Google Docs API."""
    _border = lambda: {
        "color": {},
        "width": {"unit": "PT"},
        "padding": {"unit": "PT"},
        "dashStyle": "SOLID",
    }

    normal_text = {
        "namedStyleType": "NORMAL_TEXT",
        "textStyle": {
            "bold": False, "italic": False, "underline": False,
            "strikethrough": False, "smallCaps": False,
            "backgroundColor": {},
            "foregroundColor": {"color": {"rgbColor": {}}},
            "fontSize": {"magnitude": 11, "unit": "PT"},
            "weightedFontFamily": {"fontFamily": "Arial", "weight": 400},
            "baselineOffset": "NONE",
        },
        "paragraphStyle": {
            "namedStyleType": "NORMAL_TEXT",
            "alignment": "START",
            "lineSpacing": 115,
            "direction": "LEFT_TO_RIGHT",
            "spacingMode": "COLLAPSE_LISTS",
            "spaceAbove": {"unit": "PT"},
            "spaceBelow": {"unit": "PT"},
            "borderBetween": _border(),
            "borderTop": _border(),
            "borderBottom": _border(),
            "borderLeft": _border(),
            "borderRight": _border(),
            "indentFirstLine": {"unit": "PT"},
            "indentStart": {"unit": "PT"},
            "indentEnd": {"unit": "PT"},
            "keepLinesTogether": False,
            "keepWithNext": False,
            "avoidWidowAndOrphan": True,
            "shading": {"backgroundColor": {}},
            "pageBreakBefore": False,
        },
    }

    def _heading(name, text_style, space_above, space_below):
        return {
            "namedStyleType": name,
            "textStyle": text_style,
            "paragraphStyle": {
                "namedStyleType": "NORMAL_TEXT",
                "direction": "LEFT_TO_RIGHT",
                "spaceAbove": {"magnitude": space_above, "unit": "PT"},
                "spaceBelow": {"magnitude": space_below, "unit": "PT"},
                "keepLinesTogether": True,
                "keepWithNext": True,
                "pageBreakBefore": False,
            },
        }

    _grey = {"color": {"rgbColor": {"red": 0.2627451, "green": 0.2627451, "blue": 0.2627451}}}
    _grey4 = {"color": {"rgbColor": {"red": 0.4, "green": 0.4, "blue": 0.4}}}

    return {"styles": [
        normal_text,
        _heading("HEADING_1", {"fontSize": {"magnitude": 20, "unit": "PT"}}, 20, 6),
        _heading("HEADING_2", {"bold": False, "fontSize": {"magnitude": 16, "unit": "PT"}}, 18, 6),
        _heading("HEADING_3", {"bold": False, "foregroundColor": _grey, "fontSize": {"magnitude": 14, "unit": "PT"}}, 16, 4),
        _heading("HEADING_4", {"foregroundColor": _grey4, "fontSize": {"magnitude": 12, "unit": "PT"}}, 14, 4),
        _heading("HEADING_5", {"foregroundColor": _grey4, "fontSize": {"magnitude": 11, "unit": "PT"}}, 12, 4),
        _heading("HEADING_6", {"italic": True, "foregroundColor": _grey4, "fontSize": {"magnitude": 11, "unit": "PT"}}, 12, 4),
        {
            "namedStyleType": "TITLE",
            "textStyle": {"fontSize": {"magnitude": 26, "unit": "PT"}},
            "paragraphStyle": {
                "namedStyleType": "NORMAL_TEXT", "direction": "LEFT_TO_RIGHT",
                "spaceAbove": {"unit": "PT"}, "spaceBelow": {"magnitude": 3, "unit": "PT"},
                "keepLinesTogether": True, "keepWithNext": True, "pageBreakBefore": False,
            },
        },
        {
            "namedStyleType": "SUBTITLE",
            "textStyle": {
                "italic": False, "foregroundColor": _grey4,
                "fontSize": {"magnitude": 15, "unit": "PT"},
                "weightedFontFamily": {"fontFamily": "Arial", "weight": 400},
            },
            "paragraphStyle": {
                "namedStyleType": "NORMAL_TEXT", "direction": "LEFT_TO_RIGHT",
                "spaceAbove": {"unit": "PT"}, "spaceBelow": {"magnitude": 16, "unit": "PT"},
                "keepLinesTogether": True, "keepWithNext": True, "pageBreakBefore": False,
            },
        },
    ]}


# ---------------------------------------------------------------------------
# body_to_html: body JSON → styled HTML
# ---------------------------------------------------------------------------

_ALIGNMENT_MAP = {
    "START": "left",
    "CENTER": "center",
    "END": "right",
    "JUSTIFIED": "justify",
}

_HEADING_TAG_MAP = {
    "HEADING_1": "h1",
    "HEADING_2": "h2",
    "HEADING_3": "h3",
    "HEADING_4": "h4",
    "HEADING_5": "h5",
    "HEADING_6": "h6",
    "TITLE": "h1",
    "SUBTITLE": "h2",
}


def _text_style_to_css_and_tags(ts: dict) -> tuple[str, list[str], list[str]]:
    """Convert a textStyle dict to (inline CSS, open tags, close tags)."""
    parts: list[str] = []
    open_tags: list[str] = []
    close_tags: list[str] = []

    if ts.get("bold"):
        open_tags.append("<b>")
        close_tags.insert(0, "</b>")
    if ts.get("italic"):
        open_tags.append("<i>")
        close_tags.insert(0, "</i>")
    if ts.get("underline"):
        open_tags.append("<u>")
        close_tags.insert(0, "</u>")
    if ts.get("strikethrough"):
        open_tags.append("<s>")
        close_tags.insert(0, "</s>")

    wff = ts.get("weightedFontFamily")
    if wff and wff.get("fontFamily"):
        parts.append(f"font-family: {wff['fontFamily']}")

    fs = ts.get("fontSize")
    if fs and fs.get("magnitude"):
        unit = fs.get("unit", "PT").lower().replace("pt", "pt")
        parts.append(f"font-size: {fs['magnitude']}{unit}")

    fg = ts.get("foregroundColor", {}).get("color", {}).get("rgbColor")
    if fg:
        r = int(fg.get("red", 0) * 255)
        g = int(fg.get("green", 0) * 255)
        b = int(fg.get("blue", 0) * 255)
        parts.append(f"color: rgb({r},{g},{b})")

    bg = ts.get("backgroundColor", {}).get("color", {}).get("rgbColor")
    if bg:
        r = int(bg.get("red", 0) * 255)
        g = int(bg.get("green", 0) * 255)
        b = int(bg.get("blue", 0) * 255)
        parts.append(f"background-color: rgb({r},{g},{b})")

    return "; ".join(parts), open_tags, close_tags


def _paragraph_style_to_css(ps: dict) -> str:
    """Convert a paragraphStyle dict to inline CSS."""
    parts: list[str] = []

    alignment = ps.get("alignment")
    if alignment and alignment in _ALIGNMENT_MAP:
        parts.append(f"text-align: {_ALIGNMENT_MAP[alignment]}")

    line_spacing = ps.get("lineSpacing")
    if line_spacing:
        parts.append(f"line-height: {line_spacing / 100}")

    indent_start = ps.get("indentStart", {}).get("magnitude")
    if indent_start:
        parts.append(f"margin-left: {indent_start}pt")

    indent_end = ps.get("indentEnd", {}).get("magnitude")
    if indent_end:
        parts.append(f"margin-right: {indent_end}pt")

    indent_first = ps.get("indentFirstLine", {}).get("magnitude")
    if indent_first:
        parts.append(f"text-indent: {indent_first}pt")

    space_above = ps.get("spaceAbove", {}).get("magnitude")
    if space_above:
        parts.append(f"margin-top: {space_above}pt")

    space_below = ps.get("spaceBelow", {}).get("magnitude")
    if space_below:
        parts.append(f"margin-bottom: {space_below}pt")

    return "; ".join(parts)


def _render_paragraph_spans(para: dict) -> list[str]:
    """Render inline spans for a paragraph's elements."""
    spans: list[str] = []
    for pe in para.get("elements", []):
        tr = pe.get("textRun")
        if not tr:
            continue
        content = tr.get("content", "")
        # Strip trailing newline that Google Docs adds to each paragraph
        content = content.rstrip("\n")
        if not content:
            continue

        ts = tr.get("textStyle", {})
        css, open_tags, close_tags = _text_style_to_css_and_tags(ts)

        escaped = html_mod.escape(content)
        if css:
            span = f'<span style="{css}">{"".join(open_tags)}{escaped}{"".join(close_tags)}</span>'
        elif open_tags:
            span = f'{"".join(open_tags)}{escaped}{"".join(close_tags)}'
        else:
            span = escaped
        spans.append(span)
    return spans


def body_to_html(body: dict | None) -> str:
    """Convert a Google Docs body JSON to styled HTML for the editor."""
    if not body:
        return ""

    result: list[str] = []
    in_list: str | None = None  # "ul" or "ol" when inside a list

    content_elements = body.get("content", [])
    for element in content_elements:
        para = element.get("paragraph")
        if not para:
            continue

        bullet = para.get("bullet")
        if bullet:
            glyph = bullet.get("glyphType", "")
            list_tag = "ol" if glyph in ("DECIMAL", "ALPHA", "ROMAN") else "ul"

            if in_list != list_tag:
                if in_list:
                    result.append(f"</{in_list}>")
                result.append(f"<{list_tag}>")
                in_list = list_tag

            spans = _render_paragraph_spans(para)
            inner = "".join(spans) if spans else "<br>"
            result.append(f"<li>{inner}</li>")
            continue

        # Not a list paragraph — close any open list
        if in_list:
            result.append(f"</{in_list}>")
            in_list = None

        ps = para.get("paragraphStyle", {})
        named_style = ps.get("namedStyleType", "NORMAL_TEXT")
        tag = _HEADING_TAG_MAP.get(named_style, "p")

        para_css = _paragraph_style_to_css(ps)
        style_attr = f' style="{para_css}"' if para_css else ""

        spans = _render_paragraph_spans(para)
        if spans:
            result.append(f"<{tag}{style_attr}>{''.join(spans)}</{tag}>")
        else:
            result.append(f"<{tag}{style_attr}><br></{tag}>")

    # Close any trailing open list
    if in_list:
        result.append(f"</{in_list}>")

    return "\n".join(result)


# ---------------------------------------------------------------------------
# html_to_body: editor HTML → body JSON
# ---------------------------------------------------------------------------

_CSS_ALIGN_MAP = {
    "left": "START",
    "center": "CENTER",
    "right": "END",
    "justify": "JUSTIFIED",
}

_TAG_TO_NAMED_STYLE = {
    "h1": "HEADING_1",
    "h2": "HEADING_2",
    "h3": "HEADING_3",
    "h4": "HEADING_4",
    "h5": "HEADING_5",
    "h6": "HEADING_6",
}


def _parse_inline_style(style_str: str) -> dict[str, str]:
    """Parse an inline style string into a dict."""
    result: dict[str, str] = {}
    if not style_str:
        return result
    for part in style_str.split(";"):
        part = part.strip()
        if ":" not in part:
            continue
        key, val = part.split(":", 1)
        result[key.strip().lower()] = val.strip()
    return result


def _parse_css_color(color_str: str) -> dict | None:
    """Parse 'rgb(r,g,b)' or '#rrggbb' into rgbColor dict (0.0-1.0)."""
    m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", color_str)
    if m:
        return {
            "red": int(m.group(1)) / 255,
            "green": int(m.group(2)) / 255,
            "blue": int(m.group(3)) / 255,
        }
    m = re.match(r"#([0-9a-fA-F]{6})", color_str)
    if m:
        hex_str = m.group(1)
        return {
            "red": int(hex_str[0:2], 16) / 255,
            "green": int(hex_str[2:4], 16) / 255,
            "blue": int(hex_str[4:6], 16) / 255,
        }
    return None


def _extract_text_style_from_element(el) -> dict:
    """Extract text style from an HTML element and its inline style."""
    ts: dict = {}

    # Check tag-based styles
    tag = el.name if el.name else ""
    ancestors = [p.name for p in el.parents if p.name]

    if tag == "b" or tag == "strong" or "b" in ancestors or "strong" in ancestors:
        ts["bold"] = True
    if tag == "i" or tag == "em" or "i" in ancestors or "em" in ancestors:
        ts["italic"] = True
    if tag == "u" or "u" in ancestors:
        ts["underline"] = True
    if tag == "s" or tag == "strike" or "s" in ancestors or "strike" in ancestors:
        ts["strikethrough"] = True

    # Check inline style
    style_str = el.get("style", "") if el.name else ""
    # Also check parent span styles
    for parent in el.parents:
        if parent.name == "span" and parent.get("style"):
            style_str = parent.get("style", "") + ";" + style_str
            break

    styles = _parse_inline_style(style_str)

    ff = styles.get("font-family")
    if ff:
        ff = ff.strip("'\"")
        ts["weightedFontFamily"] = {"fontFamily": ff, "weight": 400}

    fs = styles.get("font-size")
    if fs:
        m = re.match(r"([\d.]+)\s*(pt|px|em|rem)?", fs, re.IGNORECASE)
        if m:
            mag = float(m.group(1))
            unit = (m.group(2) or "pt").upper().replace("PX", "PT")
            ts["fontSize"] = {"magnitude": mag, "unit": unit}

    color = styles.get("color")
    if color:
        rgb = _parse_css_color(color)
        if rgb:
            ts["foregroundColor"] = {"color": {"rgbColor": rgb}}

    bg = styles.get("background-color")
    if bg:
        rgb = _parse_css_color(bg)
        if rgb:
            ts["backgroundColor"] = {"color": {"rgbColor": rgb}}

    fw = styles.get("font-weight")
    if fw and fw not in ("normal", "400"):
        ts["bold"] = True

    fst = styles.get("font-style")
    if fst == "italic":
        ts["italic"] = True

    td = styles.get("text-decoration")
    if td and "underline" in td:
        ts["underline"] = True
    if td and "line-through" in td:
        ts["strikethrough"] = True

    return ts


def _extract_paragraph_style(el) -> dict:
    """Extract paragraph-level styles from a block element."""
    ps: dict = {}

    tag = el.name.lower() if el.name else ""
    if tag in _TAG_TO_NAMED_STYLE:
        ps["namedStyleType"] = _TAG_TO_NAMED_STYLE[tag]
    else:
        ps["namedStyleType"] = "NORMAL_TEXT"

    styles = _parse_inline_style(el.get("style", ""))

    ta = styles.get("text-align")
    if ta and ta in _CSS_ALIGN_MAP:
        ps["alignment"] = _CSS_ALIGN_MAP[ta]

    lh = styles.get("line-height")
    if lh:
        try:
            val = float(lh)
            ps["lineSpacing"] = val * 100
        except ValueError:
            pass

    ml = styles.get("margin-left")
    if ml:
        m = re.match(r"([\d.]+)\s*pt", ml)
        if m:
            ps["indentStart"] = {"magnitude": float(m.group(1)), "unit": "PT"}

    ps["direction"] = "LEFT_TO_RIGHT"
    return ps


def _collect_text_runs(el, index: int) -> tuple[list[dict], int]:
    """Recursively collect text runs from an element's children.

    Returns (list of textRun elements, next index).
    """
    from bs4 import NavigableString

    runs: list[dict] = []

    for child in el.children:
        if isinstance(child, NavigableString):
            text = str(child)
            if not text:
                continue
            # Build text style from parent chain
            ts = _extract_text_style_from_element(child)
            end = index + len(text)
            runs.append({
                "startIndex": index,
                "endIndex": end,
                "textRun": {
                    "content": text,
                    "textStyle": ts,
                },
            })
            index = end
        elif child.name in ("b", "strong", "i", "em", "u", "s", "strike", "span", "a", "font"):
            sub_runs, index = _collect_text_runs(child, index)
            # Merge parent tag styles into sub-runs
            for sr in sub_runs:
                ts = sr["textRun"]["textStyle"]
                if child.name in ("b", "strong"):
                    ts["bold"] = True
                elif child.name in ("i", "em"):
                    ts["italic"] = True
                elif child.name == "u":
                    ts["underline"] = True
                elif child.name in ("s", "strike"):
                    ts["strikethrough"] = True

                # Inline styles from span
                if child.name == "span" and child.get("style"):
                    span_styles = _parse_inline_style(child.get("style", ""))
                    ff = span_styles.get("font-family")
                    if ff:
                        ts["weightedFontFamily"] = {"fontFamily": ff.strip("'\""), "weight": 400}
                    fs_str = span_styles.get("font-size")
                    if fs_str:
                        m = re.match(r"([\d.]+)\s*(pt|px)?", fs_str, re.IGNORECASE)
                        if m:
                            ts["fontSize"] = {"magnitude": float(m.group(1)), "unit": (m.group(2) or "PT").upper()}
                    color = span_styles.get("color")
                    if color:
                        rgb = _parse_css_color(color)
                        if rgb:
                            ts["foregroundColor"] = {"color": {"rgbColor": rgb}}
                    bg = span_styles.get("background-color")
                    if bg:
                        rgb = _parse_css_color(bg)
                        if rgb:
                            ts["backgroundColor"] = {"color": {"rgbColor": rgb}}
            runs.extend(sub_runs)
        elif child.name == "br":
            pass  # Line break within paragraph — skip
        else:
            # For any other nested element, treat as text
            sub_runs, index = _collect_text_runs(child, index)
            runs.extend(sub_runs)

    return runs, index


def html_to_body(html_str: str) -> dict:
    """Convert editor HTML back to Google Docs body JSON.

    Parses HTML block elements (p, h1-h6, div) into paragraphs with
    textRun elements that carry textStyle and paragraphStyle.
    """
    from bs4 import BeautifulSoup

    if not html_str or not html_str.strip():
        return create_empty_body()

    soup = BeautifulSoup(html_str, "lxml")
    body_el = soup.body if soup.body else soup

    # Collect block-level elements (including list items from ul/ol)
    block_tags = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "div", "ul", "ol", "li"}
    raw_blocks = body_el.find_all(block_tags, recursive=False)
    if not raw_blocks:
        # Fallback: treat all children as a single paragraph
        raw_blocks = [body_el]

    # Flatten list containers: replace <ul>/<ol> with their <li> children
    blocks = []
    for b in raw_blocks:
        if b.name in ("ul", "ol"):
            for li in b.find_all("li", recursive=False):
                li["data-list-type"] = "ul" if b.name == "ul" else "ol"
                blocks.append(li)
        else:
            blocks.append(b)

    elements: list[dict] = [_SECTION_BREAK]
    index = 1

    for block in blocks:
        ps = _extract_paragraph_style(block)
        runs, index = _collect_text_runs(block, index)

        # Append newline to last run (Google Docs convention)
        if runs:
            last_run = runs[-1]
            last_run["textRun"]["content"] += "\n"
            last_run["endIndex"] += 1
            index += 1
        else:
            # Empty paragraph
            runs = [{
                "startIndex": index,
                "endIndex": index + 1,
                "textRun": {"content": "\n", "textStyle": {}},
            }]
            index += 1

        start = runs[0]["startIndex"]
        end = runs[-1]["endIndex"]

        para_dict: dict = {
            "elements": runs,
            "paragraphStyle": ps,
        }

        # Carry list/bullet info from <li> elements
        list_type = block.get("data-list-type") if block.name == "li" else None
        if list_type:
            glyph = "DECIMAL" if list_type == "ol" else "DISC"
            para_dict["bullet"] = {
                "listId": f"kix.list.{list_type}",
                "nestingLevel": 0,
                "textStyle": {},
                "glyphType": glyph,
            }

        elements.append({
            "startIndex": start,
            "endIndex": end,
            "paragraph": para_dict,
        })

    if len(elements) == 1:
        return create_empty_body()

    return {"content": elements}
