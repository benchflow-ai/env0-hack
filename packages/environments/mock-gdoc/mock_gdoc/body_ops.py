"""Index-aware body manipulation engine for Google Docs API mock.

All functions are pure: take a body dict (and related maps), return new dicts.
Index arithmetic follows the Google Docs API conventions:
  - Body indices are 1-based
  - sectionBreak at index 0 occupies [0, 1) — but represented as endIndex=1
  - paragraphs occupy [startIndex, endIndex) where endIndex is exclusive
  - tables: table start=1 idx, each row start=1 idx, each cell start=1 idx,
    cell content is regular paragraph indices, table end=1 idx
  - inlineObjectElement, pageBreak, footnoteReference each occupy 1 index
"""

from __future__ import annotations

import copy
import re
import uuid
from typing import Any


# ---------------------------------------------------------------------------
# Reindexing
# ---------------------------------------------------------------------------

def reindex_body(body: dict) -> dict:
    """Recompute all startIndex/endIndex values in the body tree.

    Walks the content list and recursively fixes indices to be consistent.
    Returns a new body dict (shallow copy of structure).
    """
    body = copy.deepcopy(body)
    idx = 0
    for elem in body.get("content", []):
        idx = _reindex_element(elem, idx)
    return body


def _reindex_element(elem: dict, idx: int) -> int:
    """Reindex a single structural element starting at *idx*. Returns next idx."""
    if "sectionBreak" in elem:
        elem.pop("startIndex", None)
        elem["endIndex"] = idx + 1
        return idx + 1

    if "paragraph" in elem:
        elem["startIndex"] = idx
        para = elem["paragraph"]
        pidx = idx
        for pe in para.get("elements", []):
            pidx = _reindex_paragraph_element(pe, pidx)
        elem["endIndex"] = pidx
        return pidx

    if "table" in elem:
        elem["startIndex"] = idx
        tidx = idx + 1  # table open char
        table = elem["table"]
        for row in table.get("tableRows", []):
            tidx = _reindex_table_row(row, tidx)
        tidx += 1  # table close char
        elem["endIndex"] = tidx
        return tidx

    if "tableOfContents" in elem:
        elem["startIndex"] = idx
        toc = elem["tableOfContents"]
        tocidx = idx + 1
        for ce in toc.get("content", []):
            tocidx = _reindex_element(ce, tocidx)
        tocidx += 1
        elem["endIndex"] = tocidx
        return tocidx

    # Unknown element — skip 1
    elem["startIndex"] = idx
    elem["endIndex"] = idx + 1
    return idx + 1


def _reindex_table_row(row: dict, idx: int) -> int:
    """Reindex a table row starting at *idx*. Returns next idx."""
    row["startIndex"] = idx
    ridx = idx + 1  # row open char
    for cell in row.get("tableCells", []):
        ridx = _reindex_table_cell(cell, ridx)
    row["endIndex"] = ridx
    return ridx


def _reindex_table_cell(cell: dict, idx: int) -> int:
    """Reindex a table cell starting at *idx*. Returns next idx."""
    cell["startIndex"] = idx
    cidx = idx + 1  # cell open char
    for ce in cell.get("content", []):
        cidx = _reindex_element(ce, cidx)
    cell["endIndex"] = cidx
    return cidx


def _reindex_paragraph_element(pe: dict, idx: int) -> int:
    """Reindex a paragraph element. Returns next idx."""
    pe["startIndex"] = idx
    if "textRun" in pe:
        length = len(pe["textRun"].get("content", ""))
        pe["endIndex"] = idx + length
        return idx + length
    # inlineObjectElement, pageBreak, footnoteReference, equation — 1 char each
    pe["endIndex"] = idx + 1
    return idx + 1


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------

def compute_body_length(body: dict) -> int:
    """Return the total index length of the body (endIndex of last element)."""
    content = body.get("content", [])
    if not content:
        return 0
    last = content[-1]
    return last.get("endIndex", 0)


def extract_plain_text(body: dict) -> str:
    """Extract plain text from body, including table cell content."""
    parts: list[str] = []
    _extract_text_from_elements(body.get("content", []), parts)
    return "".join(parts)


def _extract_text_from_elements(elements: list[dict], parts: list[str]):
    for elem in elements:
        if "paragraph" in elem:
            for pe in elem["paragraph"].get("elements", []):
                if "textRun" in pe:
                    parts.append(pe["textRun"].get("content", ""))
        elif "table" in elem:
            for row in elem["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    _extract_text_from_elements(cell.get("content", []), parts)
        elif "tableOfContents" in elem:
            _extract_text_from_elements(elem["tableOfContents"].get("content", []), parts)


def find_paragraph_at_index(body: dict, index: int) -> dict | None:
    """Return the paragraph structural element containing *index*, or None."""
    for elem in body.get("content", []):
        si = elem.get("startIndex", 0)
        ei = elem.get("endIndex", 0)
        if "paragraph" in elem and si <= index < ei:
            return elem
        if "table" in elem and si <= index < ei:
            result = _find_paragraph_in_table(elem["table"], index)
            if result:
                return result
    return None


def _find_paragraph_in_table(table: dict, index: int) -> dict | None:
    for row in table.get("tableRows", []):
        for cell in row.get("tableCells", []):
            for ce in cell.get("content", []):
                if "paragraph" in ce:
                    si = ce.get("startIndex", 0)
                    ei = ce.get("endIndex", 0)
                    if si <= index < ei:
                        return ce
    return None


def find_paragraphs_in_range(body: dict, start: int, end: int) -> list[dict]:
    """Return all paragraph structural elements overlapping [start, end)."""
    results: list[dict] = []
    _find_paragraphs_in_elements(body.get("content", []), start, end, results)
    return results


def _find_paragraphs_in_elements(
    elements: list[dict], start: int, end: int, results: list[dict]
):
    for elem in elements:
        si = elem.get("startIndex", 0)
        ei = elem.get("endIndex", 0)
        if "paragraph" in elem:
            if si < end and ei > start:
                results.append(elem)
        elif "table" in elem:
            if si < end and ei > start:
                for row in elem["table"].get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        _find_paragraphs_in_elements(
                            cell.get("content", []), start, end, results
                        )
        elif "tableOfContents" in elem:
            if si < end and ei > start:
                _find_paragraphs_in_elements(
                    elem["tableOfContents"].get("content", []), start, end, results
                )


# ---------------------------------------------------------------------------
# Text run splitting & coalescing
# ---------------------------------------------------------------------------

def _split_text_run_at(paragraph: dict, abs_index: int) -> None:
    """Split a text run in *paragraph* at absolute index *abs_index* in-place.

    If *abs_index* falls exactly on a text run boundary, this is a no-op.
    """
    elements = paragraph.get("elements", [])
    new_elements: list[dict] = []
    for pe in elements:
        if "textRun" not in pe:
            new_elements.append(pe)
            continue
        si = pe.get("startIndex", 0)
        ei = pe.get("endIndex", 0)
        if si < abs_index < ei:
            # Split here
            content = pe["textRun"]["content"]
            offset = abs_index - si
            left_content = content[:offset]
            right_content = content[offset:]
            style = copy.deepcopy(pe["textRun"].get("textStyle", {}))
            new_elements.append({
                "startIndex": si,
                "endIndex": abs_index,
                "textRun": {"content": left_content, "textStyle": copy.deepcopy(style)},
            })
            new_elements.append({
                "startIndex": abs_index,
                "endIndex": ei,
                "textRun": {"content": right_content, "textStyle": style},
            })
        else:
            new_elements.append(pe)
    paragraph["elements"] = new_elements


def _coalesce_text_runs(paragraph: dict) -> None:
    """Merge adjacent text runs with identical textStyle in-place."""
    elements = paragraph.get("elements", [])
    if len(elements) < 2:
        return
    merged: list[dict] = [elements[0]]
    for pe in elements[1:]:
        prev = merged[-1]
        if (
            "textRun" in prev
            and "textRun" in pe
            and prev["textRun"].get("textStyle", {}) == pe["textRun"].get("textStyle", {})
        ):
            prev["textRun"]["content"] += pe["textRun"]["content"]
            prev["endIndex"] = pe["endIndex"]
        else:
            merged.append(pe)
    paragraph["elements"] = merged


# ---------------------------------------------------------------------------
# Core mutations
# ---------------------------------------------------------------------------

def insert_text(body: dict, index: int, text: str, segment_id: str | None = None) -> dict:
    """Insert *text* at *index* in the body. Returns new body."""
    if not text:
        return body
    body = copy.deepcopy(body)

    # Find the paragraph containing this index
    para_elem = find_paragraph_at_index(body, index)
    if para_elem is None:
        # If index is at end of body, find the last paragraph
        content = body.get("content", [])
        for elem in reversed(content):
            if "paragraph" in elem:
                para_elem = elem
                break
        if para_elem is None:
            return body

    para = para_elem["paragraph"]

    # Find the text run containing the index, or insert at boundary
    elements = para.get("elements", [])
    inserted = False
    new_elements: list[dict] = []

    for pe in elements:
        if inserted or "textRun" not in pe:
            new_elements.append(pe)
            continue
        si = pe.get("startIndex", 0)
        ei = pe.get("endIndex", 0)
        if si <= index <= ei:
            # Insert within this text run
            content = pe["textRun"]["content"]
            offset = index - si
            new_content = content[:offset] + text + content[offset:]

            # Handle newlines: if inserted text contains \n, we may need to
            # split into multiple paragraphs. For simplicity in the engine,
            # we keep it as a single text run (Google Docs does allow \n within
            # a paragraph's text run for line breaks, but paragraph splits
            # happen at the structural level). The real API inserts text and
            # splits paragraphs at \n boundaries.
            if "\n" in text and offset < len(content):
                # Split at each newline to create paragraph breaks
                # For now, keep simple: insert all text in one text run
                pass

            pe["textRun"]["content"] = new_content
            new_elements.append(pe)
            inserted = True
        else:
            new_elements.append(pe)

    if not inserted and elements:
        # Append to last text run
        last = elements[-1]
        if "textRun" in last:
            content = last["textRun"]["content"]
            last["textRun"]["content"] = content + text
        new_elements = elements

    para["elements"] = new_elements
    return reindex_body(body)


def delete_range(body: dict, start: int, end: int) -> dict:
    """Delete content in [start, end). Returns new body."""
    if start >= end:
        return body
    body = copy.deepcopy(body)
    content = body.get("content", [])
    new_content: list[dict] = []

    for elem in content:
        si = elem.get("startIndex", 0)
        ei = elem.get("endIndex", 0)

        if "sectionBreak" in elem:
            # Never delete the initial section break
            new_content.append(elem)
            continue

        if ei <= start or si >= end:
            # Completely outside deletion range
            new_content.append(elem)
            continue

        if "paragraph" in elem:
            if start <= si and end >= ei:
                # Entire paragraph deleted — skip it unless it's the last one
                continue
            # Partial deletion within paragraph
            para = elem["paragraph"]
            _delete_in_paragraph(para, max(start, si), min(end, ei))
            # If paragraph has no elements or only empty content, keep a \n
            if not para.get("elements"):
                para["elements"] = [{
                    "startIndex": si,
                    "endIndex": si + 1,
                    "textRun": {"content": "\n", "textStyle": {}},
                }]
            new_content.append(elem)

        elif "table" in elem:
            if start <= si and end >= ei:
                # Entire table deleted
                continue
            # Partial deletion within table (delete text in cells)
            _delete_in_table(elem["table"], start, end)
            new_content.append(elem)
        else:
            new_content.append(elem)

    # Ensure we have at least one paragraph after the section break
    has_paragraph = any("paragraph" in e for e in new_content)
    if not has_paragraph:
        new_content.append({
            "startIndex": 1,
            "endIndex": 2,
            "paragraph": {
                "elements": [{
                    "startIndex": 1,
                    "endIndex": 2,
                    "textRun": {"content": "\n", "textStyle": {}},
                }],
                "paragraphStyle": {
                    "namedStyleType": "NORMAL_TEXT",
                    "direction": "LEFT_TO_RIGHT",
                },
            },
        })

    body["content"] = new_content
    return reindex_body(body)


def _delete_in_paragraph(para: dict, start: int, end: int):
    """Delete character range [start, end) within a paragraph's elements, in-place."""
    new_elements: list[dict] = []
    for pe in para.get("elements", []):
        si = pe.get("startIndex", 0)
        ei = pe.get("endIndex", 0)

        if ei <= start or si >= end:
            new_elements.append(pe)
            continue

        if "textRun" in pe:
            content = pe["textRun"]["content"]
            # Calculate which part of the content to keep
            del_start = max(0, start - si)
            del_end = min(len(content), end - si)
            new_content = content[:del_start] + content[del_end:]
            if new_content:
                pe["textRun"]["content"] = new_content
                new_elements.append(pe)
        else:
            # Non-text elements (inlineObject, pageBreak, etc.)
            if start <= si and end >= ei:
                continue  # Delete it
            new_elements.append(pe)

    para["elements"] = new_elements


def _delete_in_table(table: dict, start: int, end: int):
    """Delete text within table cells that overlap [start, end)."""
    for row in table.get("tableRows", []):
        for cell in row.get("tableCells", []):
            for ce in cell.get("content", []):
                si = ce.get("startIndex", 0)
                ei = ce.get("endIndex", 0)
                if "paragraph" in ce and si < end and ei > start:
                    _delete_in_paragraph(
                        ce["paragraph"], max(start, si), min(end, ei)
                    )
                    if not ce["paragraph"].get("elements"):
                        ce["paragraph"]["elements"] = [{
                            "startIndex": si,
                            "endIndex": si + 1,
                            "textRun": {"content": "\n", "textStyle": {}},
                        }]


def replace_all_text(
    body: dict, search: str, replace: str, match_case: bool = True
) -> tuple[dict, int]:
    """Replace all occurrences of *search* with *replace*. Returns (new body, count)."""
    if not search:
        return body, 0

    body = copy.deepcopy(body)
    count = _replace_in_elements(body.get("content", []), search, replace, match_case)
    if count > 0:
        body = reindex_body(body)
    return body, count


def _replace_in_elements(
    elements: list[dict], search: str, replace: str, match_case: bool
) -> int:
    """Replace text in a list of structural elements. Returns replacement count."""
    total = 0
    for elem in elements:
        if "paragraph" in elem:
            total += _replace_in_paragraph(elem["paragraph"], search, replace, match_case)
        elif "table" in elem:
            for row in elem["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    total += _replace_in_elements(
                        cell.get("content", []), search, replace, match_case
                    )
        elif "tableOfContents" in elem:
            total += _replace_in_elements(
                elem["tableOfContents"].get("content", []), search, replace, match_case
            )
    return total


def _replace_in_paragraph(
    para: dict, search: str, replace: str, match_case: bool
) -> int:
    """Replace text within a single paragraph's text runs. Returns count."""
    total = 0
    for pe in para.get("elements", []):
        if "textRun" not in pe:
            continue
        content = pe["textRun"]["content"]
        if match_case:
            count = content.count(search)
            if count > 0:
                pe["textRun"]["content"] = content.replace(search, replace)
                total += count
        else:
            pattern = re.compile(re.escape(search), re.IGNORECASE)
            matches = pattern.findall(content)
            if matches:
                pe["textRun"]["content"] = pattern.sub(replace, content)
                total += len(matches)
    return total


# ---------------------------------------------------------------------------
# Text style operations
# ---------------------------------------------------------------------------

def apply_text_style(
    body: dict, start: int, end: int, style: dict, fields: str
) -> dict:
    """Apply *style* to text in [start, end) for the given *fields*.

    Splits text runs at boundaries, applies style, then coalesces.
    """
    body = copy.deepcopy(body)
    paragraphs = find_paragraphs_in_range(body, start, end)

    for para_elem in paragraphs:
        para = para_elem["paragraph"]
        psi = para_elem.get("startIndex", 0)
        pei = para_elem.get("endIndex", 0)
        effective_start = max(start, psi)
        effective_end = min(end, pei)

        # Split at boundaries
        _split_text_run_at(para, effective_start)
        _split_text_run_at(para, effective_end)

        # Apply style to affected text runs
        for pe in para.get("elements", []):
            if "textRun" not in pe:
                continue
            si = pe.get("startIndex", 0)
            ei = pe.get("endIndex", 0)
            if si >= effective_start and ei <= effective_end:
                _merge_style(pe["textRun"], "textStyle", style, fields)

        _coalesce_text_runs(para)

    return reindex_body(body)


def _merge_style(target: dict, key: str, style: dict, fields: str):
    """Merge *style* into target[key] for the named *fields*.

    *fields* is a comma-separated string of field names (e.g. "bold,fontSize").
    Supports dotted paths like "fontSize.magnitude".
    """
    if key not in target:
        target[key] = {}
    existing = target[key]

    field_list = [f.strip() for f in fields.split(",") if f.strip()]
    for field in field_list:
        if "." in field:
            # Dotted path: e.g. "fontSize.magnitude"
            parts = field.split(".", 1)
            top = parts[0]
            rest = parts[1]
            if top in style:
                if top not in existing:
                    existing[top] = {}
                if isinstance(style[top], dict) and isinstance(existing[top], dict):
                    _merge_style({"sub": existing[top]}, "sub",
                                 {"sub": style[top]}, rest)
                    existing[top] = {"sub": existing[top]}["sub"]  # unwrap
                else:
                    existing[top] = copy.deepcopy(style[top])
        else:
            if field in style:
                existing[field] = copy.deepcopy(style[field])
            elif field == "*":
                # Wildcard: merge all fields
                for k, v in style.items():
                    existing[k] = copy.deepcopy(v)


# ---------------------------------------------------------------------------
# Paragraph style operations
# ---------------------------------------------------------------------------

def apply_paragraph_style(
    body: dict, start: int, end: int, style: dict, fields: str
) -> dict:
    """Apply *style* to paragraphs overlapping [start, end)."""
    body = copy.deepcopy(body)
    paragraphs = find_paragraphs_in_range(body, start, end)

    for para_elem in paragraphs:
        para = para_elem["paragraph"]
        if "paragraphStyle" not in para:
            para["paragraphStyle"] = {}
        _merge_style(para, "paragraphStyle", style, fields)

    return body  # No reindex needed for style-only changes


# ---------------------------------------------------------------------------
# Lists (bullets)
# ---------------------------------------------------------------------------

_BULLET_PRESETS = {
    "BULLET_DISC_CIRCLE_SQUARE": [
        {"glyphType": "GLYPH_TYPE_UNSPECIFIED", "glyphSymbol": "●"},
        {"glyphType": "GLYPH_TYPE_UNSPECIFIED", "glyphSymbol": "○"},
        {"glyphType": "GLYPH_TYPE_UNSPECIFIED", "glyphSymbol": "■"},
    ],
    "BULLET_DIAMONDX_ARROW3D_SQUARE": [
        {"glyphType": "GLYPH_TYPE_UNSPECIFIED", "glyphSymbol": "❖"},
        {"glyphType": "GLYPH_TYPE_UNSPECIFIED", "glyphSymbol": "➤"},
        {"glyphType": "GLYPH_TYPE_UNSPECIFIED", "glyphSymbol": "■"},
    ],
    "BULLET_CHECKBOX": [
        {"glyphType": "GLYPH_TYPE_UNSPECIFIED", "glyphSymbol": "☐"},
    ],
    "NUMBERED_DECIMAL_ALPHA_ROMAN": [
        {"glyphType": "DECIMAL", "glyphFormat": "%0."},
        {"glyphType": "ALPHA", "glyphFormat": "%1."},
        {"glyphType": "ROMAN", "glyphFormat": "%2."},
    ],
    "NUMBERED_DECIMAL_ALPHA_ROMAN_PARENS": [
        {"glyphType": "DECIMAL", "glyphFormat": "%0)"},
        {"glyphType": "ALPHA", "glyphFormat": "%1)"},
        {"glyphType": "ROMAN", "glyphFormat": "%2)"},
    ],
    "NUMBERED_DECIMAL_NESTED": [
        {"glyphType": "DECIMAL", "glyphFormat": "%0."},
        {"glyphType": "DECIMAL", "glyphFormat": "%0.%1."},
        {"glyphType": "DECIMAL", "glyphFormat": "%0.%1.%2."},
    ],
    "NUMBERED_UPPERALPHA_ALPHA_ROMAN": [
        {"glyphType": "UPPER_ALPHA", "glyphFormat": "%0."},
        {"glyphType": "ALPHA", "glyphFormat": "%1."},
        {"glyphType": "ROMAN", "glyphFormat": "%2."},
    ],
    "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL": [
        {"glyphType": "UPPER_ROMAN", "glyphFormat": "%0."},
        {"glyphType": "UPPER_ALPHA", "glyphFormat": "%1."},
        {"glyphType": "DECIMAL", "glyphFormat": "%2."},
    ],
    "NUMBERED_ZERODECIMAL_ALPHA_ROMAN": [
        {"glyphType": "ZERO_DECIMAL", "glyphFormat": "%0."},
        {"glyphType": "ALPHA", "glyphFormat": "%1."},
        {"glyphType": "ROMAN", "glyphFormat": "%2."},
    ],
}


def create_paragraph_bullets(
    body: dict, lists: dict, start: int, end: int, preset: str
) -> tuple[dict, dict]:
    """Apply bullet preset to paragraphs in [start, end).

    Returns (new_body, new_lists).
    """
    body = copy.deepcopy(body)
    lists = copy.deepcopy(lists)

    list_id = f"kix.{uuid.uuid4().hex[:12]}"
    nesting_levels = _BULLET_PRESETS.get(preset, _BULLET_PRESETS["BULLET_DISC_CIRCLE_SQUARE"])

    # Create list entry
    lists[list_id] = {
        "listProperties": {
            "nestingLevels": [
                {
                    "bulletAlignment": "START",
                    "indentFirstLine": {"magnitude": 18 * (i + 1), "unit": "PT"},
                    "indentStart": {"magnitude": 36 * (i + 1), "unit": "PT"},
                    "startNumber": level.get("startNumber", 1) if "glyphFormat" in level else 1,
                    **{k: v for k, v in level.items() if k != "startNumber"},
                }
                for i, level in enumerate(nesting_levels)
            ]
        }
    }

    # Apply to paragraphs
    paragraphs = find_paragraphs_in_range(body, start, end)
    for para_elem in paragraphs:
        para = para_elem["paragraph"]
        if "paragraphStyle" not in para:
            para["paragraphStyle"] = {}
        # Remove existing bullet if any
        para["paragraphStyle"].pop("bullet", None)
        # Set bullet
        para.setdefault("bullet", {})
        para["bullet"] = {"listId": list_id, "nestingLevel": 0}

    return body, lists


def delete_paragraph_bullets(
    body: dict, lists: dict, start: int, end: int
) -> tuple[dict, dict]:
    """Remove bullets from paragraphs in [start, end).

    Returns (new_body, new_lists).
    """
    body = copy.deepcopy(body)
    lists = copy.deepcopy(lists)

    used_list_ids: set[str] = set()
    paragraphs = find_paragraphs_in_range(body, start, end)

    for para_elem in paragraphs:
        para = para_elem["paragraph"]
        para.pop("bullet", None)

    # Collect all still-used list IDs
    _collect_list_ids(body.get("content", []), used_list_ids)

    # Remove orphaned lists
    orphaned = [lid for lid in lists if lid not in used_list_ids]
    for lid in orphaned:
        del lists[lid]

    return body, lists


def _collect_list_ids(elements: list[dict], ids: set[str]):
    for elem in elements:
        if "paragraph" in elem:
            bullet = elem["paragraph"].get("bullet")
            if bullet and "listId" in bullet:
                ids.add(bullet["listId"])
        elif "table" in elem:
            for row in elem["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    _collect_list_ids(cell.get("content", []), ids)


# ---------------------------------------------------------------------------
# Table operations
# ---------------------------------------------------------------------------

def _make_empty_cell_content(start_index: int = 0) -> list[dict]:
    """Create a single empty paragraph for a table cell."""
    return [{
        "startIndex": start_index,
        "endIndex": start_index + 1,
        "paragraph": {
            "elements": [{
                "startIndex": start_index,
                "endIndex": start_index + 1,
                "textRun": {"content": "\n", "textStyle": {}},
            }],
            "paragraphStyle": {
                "namedStyleType": "NORMAL_TEXT",
                "direction": "LEFT_TO_RIGHT",
            },
        },
    }]


def _make_empty_cell(start_index: int = 0) -> dict:
    return {
        "startIndex": start_index,
        "endIndex": start_index + 2,  # cell open + paragraph \n
        "content": _make_empty_cell_content(start_index + 1),
        "tableCellStyle": {
            "contentAlignment": "TOP",
            "paddingLeft": {"magnitude": 5, "unit": "PT"},
            "paddingRight": {"magnitude": 5, "unit": "PT"},
            "paddingTop": {"magnitude": 5, "unit": "PT"},
            "paddingBottom": {"magnitude": 5, "unit": "PT"},
        },
    }


def insert_table(body: dict, index: int, rows: int, cols: int) -> dict:
    """Insert a table with *rows* x *cols* at *index*. Returns new body."""
    body = copy.deepcopy(body)

    # Build table structure (indices will be fixed by reindex)
    table_rows = []
    for r in range(rows):
        cells = []
        for c in range(cols):
            cells.append(_make_empty_cell())
        table_rows.append({
            "startIndex": 0,
            "endIndex": 0,
            "tableCells": cells,
            "tableRowStyle": {"minRowHeight": {"magnitude": 0, "unit": "PT"}},
        })

    table_elem = {
        "startIndex": index,
        "endIndex": index,  # Will be fixed by reindex
        "table": {
            "rows": rows,
            "columns": cols,
            "tableRows": table_rows,
            "tableStyle": {
                "tableColumnProperties": [
                    {"widthType": "EVENLY_DISTRIBUTED"} for _ in range(cols)
                ]
            },
        },
    }

    # Find where to insert: split paragraph if needed
    content = body.get("content", [])
    new_content: list[dict] = []
    inserted = False

    for elem in content:
        if inserted:
            new_content.append(elem)
            continue

        si = elem.get("startIndex", 0)
        ei = elem.get("endIndex", 0)

        if "paragraph" in elem and si <= index <= ei:
            # Split paragraph at index and insert table between
            before, after = _split_paragraph_at_index(elem, index)
            if before:
                new_content.append(before)
            new_content.append(table_elem)
            if after:
                new_content.append(after)
            inserted = True
        elif si >= index and not inserted:
            new_content.append(table_elem)
            new_content.append(elem)
            inserted = True
        else:
            new_content.append(elem)

    if not inserted:
        new_content.append(table_elem)

    body["content"] = new_content
    return reindex_body(body)


def _split_paragraph_at_index(para_elem: dict, index: int) -> tuple[dict | None, dict | None]:
    """Split a paragraph structural element at *index*.

    Returns (before_elem, after_elem). Either can be None if the split
    is at the very start or end.
    """
    si = para_elem.get("startIndex", 0)
    ei = para_elem.get("endIndex", 0)
    para = para_elem["paragraph"]

    if index <= si:
        return None, para_elem
    if index >= ei:
        return para_elem, None

    # Split elements
    before_elements: list[dict] = []
    after_elements: list[dict] = []

    for pe in para.get("elements", []):
        psi = pe.get("startIndex", 0)
        pei = pe.get("endIndex", 0)
        if pei <= index:
            before_elements.append(pe)
        elif psi >= index:
            after_elements.append(pe)
        elif "textRun" in pe:
            # Split this text run
            content = pe["textRun"]["content"]
            offset = index - psi
            style = copy.deepcopy(pe["textRun"].get("textStyle", {}))
            if offset > 0:
                before_elements.append({
                    "startIndex": psi,
                    "endIndex": index,
                    "textRun": {"content": content[:offset], "textStyle": copy.deepcopy(style)},
                })
            if offset < len(content):
                after_elements.append({
                    "startIndex": index,
                    "endIndex": pei,
                    "textRun": {"content": content[offset:], "textStyle": style},
                })
        else:
            # Non-text element at the split point — keep in before
            before_elements.append(pe)

    pstyle = copy.deepcopy(para.get("paragraphStyle", {}))
    bullet = copy.deepcopy(para.get("bullet")) if "bullet" in para else None

    before_elem = None
    after_elem = None

    if before_elements:
        # Ensure before ends with \n
        last_be = before_elements[-1]
        if "textRun" in last_be and not last_be["textRun"]["content"].endswith("\n"):
            last_be["textRun"]["content"] += "\n"
        bp = {"elements": before_elements, "paragraphStyle": copy.deepcopy(pstyle)}
        if bullet:
            bp["bullet"] = copy.deepcopy(bullet)
        before_elem = {"startIndex": si, "endIndex": index, "paragraph": bp}

    if after_elements:
        ap = {"elements": after_elements, "paragraphStyle": pstyle}
        if bullet:
            ap["bullet"] = bullet
        after_elem = {"startIndex": index, "endIndex": ei, "paragraph": ap}

    return before_elem, after_elem


def insert_table_row(
    body: dict, table_start_index: int, row_index: int, insert_below: bool
) -> dict:
    """Insert a row in the table at *table_start_index*."""
    body = copy.deepcopy(body)
    table_elem = _find_table_at_index(body, table_start_index)
    if not table_elem:
        return body

    table = table_elem["table"]
    cols = table.get("columns", 1)
    new_row = {
        "startIndex": 0,
        "endIndex": 0,
        "tableCells": [_make_empty_cell() for _ in range(cols)],
        "tableRowStyle": {"minRowHeight": {"magnitude": 0, "unit": "PT"}},
    }

    insert_at = row_index + (1 if insert_below else 0)
    table["tableRows"].insert(insert_at, new_row)
    table["rows"] = len(table["tableRows"])

    return reindex_body(body)


def insert_table_column(
    body: dict, table_start_index: int, col_index: int, insert_right: bool
) -> dict:
    """Insert a column in the table at *table_start_index*."""
    body = copy.deepcopy(body)
    table_elem = _find_table_at_index(body, table_start_index)
    if not table_elem:
        return body

    table = table_elem["table"]
    insert_at = col_index + (1 if insert_right else 0)

    for row in table.get("tableRows", []):
        row["tableCells"].insert(insert_at, _make_empty_cell())

    table["columns"] = len(table["tableRows"][0]["tableCells"]) if table["tableRows"] else 0

    # Update tableColumnProperties
    if "tableStyle" in table and "tableColumnProperties" in table["tableStyle"]:
        table["tableStyle"]["tableColumnProperties"].insert(
            insert_at, {"widthType": "EVENLY_DISTRIBUTED"}
        )

    return reindex_body(body)


def delete_table_row(body: dict, table_start_index: int, row_index: int) -> dict:
    """Delete a row from the table."""
    body = copy.deepcopy(body)
    table_elem = _find_table_at_index(body, table_start_index)
    if not table_elem:
        return body

    table = table_elem["table"]
    rows = table.get("tableRows", [])
    if 0 <= row_index < len(rows) and len(rows) > 1:
        rows.pop(row_index)
        table["rows"] = len(rows)

    return reindex_body(body)


def delete_table_column(body: dict, table_start_index: int, col_index: int) -> dict:
    """Delete a column from the table."""
    body = copy.deepcopy(body)
    table_elem = _find_table_at_index(body, table_start_index)
    if not table_elem:
        return body

    table = table_elem["table"]
    for row in table.get("tableRows", []):
        cells = row.get("tableCells", [])
        if 0 <= col_index < len(cells) and len(cells) > 1:
            cells.pop(col_index)

    table["columns"] = len(table["tableRows"][0]["tableCells"]) if table["tableRows"] else 0

    if "tableStyle" in table and "tableColumnProperties" in table["tableStyle"]:
        props = table["tableStyle"]["tableColumnProperties"]
        if 0 <= col_index < len(props):
            props.pop(col_index)

    return reindex_body(body)


def merge_table_cells(
    body: dict, table_start_index: int,
    row_index: int, col_index: int, row_span: int, col_span: int
) -> dict:
    """Merge cells in a rectangular region."""
    body = copy.deepcopy(body)
    table_elem = _find_table_at_index(body, table_start_index)
    if not table_elem:
        return body

    table = table_elem["table"]
    rows = table.get("tableRows", [])

    # Set rowSpan/colSpan on the anchor cell
    for r in range(row_index, min(row_index + row_span, len(rows))):
        for c in range(col_index, min(col_index + col_span, len(rows[r].get("tableCells", [])))):
            cell = rows[r]["tableCells"][c]
            if r == row_index and c == col_index:
                style = cell.get("tableCellStyle", {})
                style["rowSpan"] = row_span
                style["columnSpan"] = col_span
                cell["tableCellStyle"] = style
            else:
                # Merged-away cells: clear content, mark as spanned
                cell["content"] = _make_empty_cell_content()
                style = cell.get("tableCellStyle", {})
                style["rowSpan"] = 1
                style["columnSpan"] = 1
                cell["tableCellStyle"] = style

    return reindex_body(body)


def unmerge_table_cells(
    body: dict, table_start_index: int,
    row_index: int, col_index: int, row_span: int, col_span: int
) -> dict:
    """Unmerge cells in a rectangular region."""
    body = copy.deepcopy(body)
    table_elem = _find_table_at_index(body, table_start_index)
    if not table_elem:
        return body

    table = table_elem["table"]
    rows = table.get("tableRows", [])

    for r in range(row_index, min(row_index + row_span, len(rows))):
        for c in range(col_index, min(col_index + col_span, len(rows[r].get("tableCells", [])))):
            cell = rows[r]["tableCells"][c]
            style = cell.get("tableCellStyle", {})
            style.pop("rowSpan", None)
            style.pop("columnSpan", None)
            cell["tableCellStyle"] = style

    return reindex_body(body)


def update_table_cell_style(
    body: dict, table_start_index: int,
    row_index: int, col_index: int, row_span: int, col_span: int,
    style: dict, fields: str
) -> dict:
    """Update cell style for cells in a rectangular region."""
    body = copy.deepcopy(body)
    table_elem = _find_table_at_index(body, table_start_index)
    if not table_elem:
        return body

    table = table_elem["table"]
    rows = table.get("tableRows", [])

    for r in range(row_index, min(row_index + row_span, len(rows))):
        for c in range(col_index, min(col_index + col_span, len(rows[r].get("tableCells", [])))):
            cell = rows[r]["tableCells"][c]
            _merge_style(cell, "tableCellStyle", style, fields)

    return body


def update_table_column_properties(
    body: dict, table_start_index: int,
    col_indices: list[int], properties: dict, fields: str
) -> dict:
    """Update column properties for specified columns."""
    body = copy.deepcopy(body)
    table_elem = _find_table_at_index(body, table_start_index)
    if not table_elem:
        return body

    table = table_elem["table"]
    style = table.get("tableStyle", {})
    props = style.get("tableColumnProperties", [])

    for ci in col_indices:
        if 0 <= ci < len(props):
            _merge_style({"p": props[ci]}, "p", properties, fields)
            props[ci] = {"p": props[ci]}["p"]  # unwrap

    return body


def update_table_row_style(
    body: dict, table_start_index: int,
    row_indices: list[int], style: dict, fields: str
) -> dict:
    """Update row style for specified rows."""
    body = copy.deepcopy(body)
    table_elem = _find_table_at_index(body, table_start_index)
    if not table_elem:
        return body

    table = table_elem["table"]
    rows = table.get("tableRows", [])

    for ri in row_indices:
        if 0 <= ri < len(rows):
            _merge_style(rows[ri], "tableRowStyle", style, fields)

    return body


def _find_table_at_index(body: dict, index: int) -> dict | None:
    """Find the table structural element whose startIndex == *index*."""
    for elem in body.get("content", []):
        if "table" in elem and elem.get("startIndex") == index:
            return elem
    return None


# ---------------------------------------------------------------------------
# Page break, section break
# ---------------------------------------------------------------------------

def insert_page_break(body: dict, index: int) -> dict:
    """Insert a page break at *index*. Returns new body."""
    body = copy.deepcopy(body)
    para_elem = find_paragraph_at_index(body, index)
    if not para_elem:
        return body

    para = para_elem["paragraph"]
    # Insert a pageBreak element at the index
    _split_text_run_at(para, index)

    new_elements: list[dict] = []
    inserted = False
    for pe in para.get("elements", []):
        si = pe.get("startIndex", 0)
        if not inserted and si >= index:
            new_elements.append({
                "startIndex": index,
                "endIndex": index + 1,
                "pageBreak": {"textStyle": {}},
            })
            inserted = True
        new_elements.append(pe)

    if not inserted:
        new_elements.append({
            "startIndex": index,
            "endIndex": index + 1,
            "pageBreak": {"textStyle": {}},
        })

    para["elements"] = new_elements
    return reindex_body(body)


def insert_section_break(
    body: dict, index: int, section_type: str = "CONTINUOUS"
) -> dict:
    """Insert a section break at *index*. Returns new body."""
    body = copy.deepcopy(body)
    content = body.get("content", [])
    new_content: list[dict] = []
    inserted = False

    section_elem = {
        "endIndex": index + 1,
        "sectionBreak": {
            "sectionStyle": {
                "columnSeparatorStyle": "NONE",
                "contentDirection": "LEFT_TO_RIGHT",
                "sectionType": section_type,
            }
        },
    }

    for elem in content:
        if inserted:
            new_content.append(elem)
            continue

        si = elem.get("startIndex", 0)
        ei = elem.get("endIndex", 0)

        if "paragraph" in elem and si <= index <= ei:
            before, after = _split_paragraph_at_index(elem, index)
            if before:
                new_content.append(before)
            new_content.append(section_elem)
            if after:
                new_content.append(after)
            else:
                # Add empty paragraph after section break
                new_content.append({
                    "startIndex": 0, "endIndex": 0,
                    "paragraph": {
                        "elements": [{"startIndex": 0, "endIndex": 1, "textRun": {"content": "\n", "textStyle": {}}}],
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT", "direction": "LEFT_TO_RIGHT"},
                    },
                })
            inserted = True
        elif si >= index and not inserted:
            new_content.append(section_elem)
            new_content.append(elem)
            inserted = True
        else:
            new_content.append(elem)

    if not inserted:
        new_content.append(section_elem)

    body["content"] = new_content
    return reindex_body(body)


# ---------------------------------------------------------------------------
# Inline images
# ---------------------------------------------------------------------------

def insert_inline_image(
    body: dict, inline_objects: dict, index: int,
    uri: str, size: dict | None = None
) -> tuple[dict, dict, str]:
    """Insert an inline image at *index*.

    Returns (new_body, new_inline_objects, object_id).
    """
    body = copy.deepcopy(body)
    inline_objects = copy.deepcopy(inline_objects)

    object_id = f"kix.{uuid.uuid4().hex[:12]}"

    # Add to inline objects map
    inline_objects[object_id] = {
        "objectId": object_id,
        "inlineObjectProperties": {
            "embeddedObject": {
                "imageProperties": {
                    "contentUri": uri,
                    "sourceUri": uri,
                },
                "size": size or {
                    "width": {"magnitude": 200, "unit": "PT"},
                    "height": {"magnitude": 150, "unit": "PT"},
                },
                "embeddedObjectBorder": {
                    "color": {},
                    "width": {"unit": "PT"},
                    "dashStyle": "SOLID",
                    "propertyState": "NOT_RENDERED",
                },
            }
        },
    }

    # Insert inlineObjectElement in the paragraph at index
    para_elem = find_paragraph_at_index(body, index)
    if para_elem:
        para = para_elem["paragraph"]
        _split_text_run_at(para, index)

        new_elements: list[dict] = []
        inserted = False
        for pe in para.get("elements", []):
            si = pe.get("startIndex", 0)
            if not inserted and si >= index:
                new_elements.append({
                    "startIndex": index,
                    "endIndex": index + 1,
                    "inlineObjectElement": {
                        "inlineObjectId": object_id,
                        "textStyle": {},
                    },
                })
                inserted = True
            new_elements.append(pe)

        if not inserted:
            new_elements.append({
                "startIndex": index,
                "endIndex": index + 1,
                "inlineObjectElement": {
                    "inlineObjectId": object_id,
                    "textStyle": {},
                },
            })

        para["elements"] = new_elements

    body = reindex_body(body)
    return body, inline_objects, object_id


# ---------------------------------------------------------------------------
# Headers & Footers
# ---------------------------------------------------------------------------

def create_header(
    body: dict, headers: dict, header_type: str = "DEFAULT",
    section_index: int = 0
) -> tuple[dict, dict, str]:
    """Create a header. Returns (body, new_headers, header_id)."""
    body = copy.deepcopy(body)
    headers = copy.deepcopy(headers)

    header_id = f"kix.{uuid.uuid4().hex[:12]}"
    headers[header_id] = {
        "headerId": header_id,
        "content": [
            {
                "startIndex": 0,
                "endIndex": 1,
                "paragraph": {
                    "elements": [{
                        "startIndex": 0,
                        "endIndex": 1,
                        "textRun": {"content": "\n", "textStyle": {}},
                    }],
                    "paragraphStyle": {
                        "namedStyleType": "NORMAL_TEXT",
                        "direction": "LEFT_TO_RIGHT",
                    },
                },
            }
        ],
    }

    # Link to section break's sectionStyle
    for elem in body.get("content", []):
        if "sectionBreak" in elem:
            ss = elem["sectionBreak"].get("sectionStyle", {})
            if header_type == "DEFAULT":
                ss["defaultHeaderId"] = header_id
            elif header_type == "FIRST_PAGE":
                ss["firstPageHeaderId"] = header_id
            elif header_type == "EVEN_PAGE":
                ss["evenPageHeaderId"] = header_id
            elem["sectionBreak"]["sectionStyle"] = ss
            break  # Apply to first section for simplicity

    return body, headers, header_id


def create_footer(
    body: dict, footers: dict, footer_type: str = "DEFAULT",
    section_index: int = 0
) -> tuple[dict, dict, str]:
    """Create a footer. Returns (body, new_footers, footer_id)."""
    body = copy.deepcopy(body)
    footers = copy.deepcopy(footers)

    footer_id = f"kix.{uuid.uuid4().hex[:12]}"
    footers[footer_id] = {
        "footerId": footer_id,
        "content": [
            {
                "startIndex": 0,
                "endIndex": 1,
                "paragraph": {
                    "elements": [{
                        "startIndex": 0,
                        "endIndex": 1,
                        "textRun": {"content": "\n", "textStyle": {}},
                    }],
                    "paragraphStyle": {
                        "namedStyleType": "NORMAL_TEXT",
                        "direction": "LEFT_TO_RIGHT",
                    },
                },
            }
        ],
    }

    for elem in body.get("content", []):
        if "sectionBreak" in elem:
            ss = elem["sectionBreak"].get("sectionStyle", {})
            if footer_type == "DEFAULT":
                ss["defaultFooterId"] = footer_id
            elif footer_type == "FIRST_PAGE":
                ss["firstPageFooterId"] = footer_id
            elif footer_type == "EVEN_PAGE":
                ss["evenPageFooterId"] = footer_id
            elem["sectionBreak"]["sectionStyle"] = ss
            break

    return body, footers, footer_id


def delete_header(body: dict, headers: dict, header_id: str) -> tuple[dict, dict]:
    """Delete a header. Returns (body, new_headers)."""
    body = copy.deepcopy(body)
    headers = copy.deepcopy(headers)
    headers.pop(header_id, None)

    # Remove references from section breaks
    for elem in body.get("content", []):
        if "sectionBreak" in elem:
            ss = elem["sectionBreak"].get("sectionStyle", {})
            for key in ["defaultHeaderId", "firstPageHeaderId", "evenPageHeaderId"]:
                if ss.get(key) == header_id:
                    del ss[key]

    return body, headers


def delete_footer(body: dict, footers: dict, footer_id: str) -> tuple[dict, dict]:
    """Delete a footer. Returns (body, new_footers)."""
    body = copy.deepcopy(body)
    footers = copy.deepcopy(footers)
    footers.pop(footer_id, None)

    for elem in body.get("content", []):
        if "sectionBreak" in elem:
            ss = elem["sectionBreak"].get("sectionStyle", {})
            for key in ["defaultFooterId", "firstPageFooterId", "evenPageFooterId"]:
                if ss.get(key) == footer_id:
                    del ss[key]

    return body, footers


# ---------------------------------------------------------------------------
# Footnotes
# ---------------------------------------------------------------------------

def create_footnote(
    body: dict, footnotes: dict, index: int
) -> tuple[dict, dict, str]:
    """Create a footnote at *index*. Returns (body, footnotes, footnote_id)."""
    body = copy.deepcopy(body)
    footnotes = copy.deepcopy(footnotes)

    footnote_id = f"kix.{uuid.uuid4().hex[:12]}"
    footnotes[footnote_id] = {
        "footnoteId": footnote_id,
        "content": [
            {
                "startIndex": 0,
                "endIndex": 1,
                "paragraph": {
                    "elements": [{
                        "startIndex": 0,
                        "endIndex": 1,
                        "textRun": {"content": "\n", "textStyle": {}},
                    }],
                    "paragraphStyle": {
                        "namedStyleType": "NORMAL_TEXT",
                        "direction": "LEFT_TO_RIGHT",
                    },
                },
            }
        ],
    }

    # Insert footnoteReference in paragraph at index
    para_elem = find_paragraph_at_index(body, index)
    if para_elem:
        para = para_elem["paragraph"]
        _split_text_run_at(para, index)

        new_elements: list[dict] = []
        inserted = False
        for pe in para.get("elements", []):
            si = pe.get("startIndex", 0)
            if not inserted and si >= index:
                new_elements.append({
                    "startIndex": index,
                    "endIndex": index + 1,
                    "footnoteReference": {
                        "footnoteId": footnote_id,
                        "footnoteNumber": str(len(footnotes)),
                        "textStyle": {"baselineOffset": "SUPERSCRIPT", "fontSize": {"magnitude": 8, "unit": "PT"}},
                    },
                })
                inserted = True
            new_elements.append(pe)

        if not inserted:
            new_elements.append({
                "startIndex": index,
                "endIndex": index + 1,
                "footnoteReference": {
                    "footnoteId": footnote_id,
                    "footnoteNumber": str(len(footnotes)),
                    "textStyle": {"baselineOffset": "SUPERSCRIPT"},
                },
            })

        para["elements"] = new_elements

    body = reindex_body(body)
    return body, footnotes, footnote_id


# ---------------------------------------------------------------------------
# Named ranges
# ---------------------------------------------------------------------------

def create_named_range(
    named_ranges: dict, name: str, start: int, end: int
) -> tuple[dict, str]:
    """Create a named range. Returns (new_named_ranges, range_id)."""
    named_ranges = copy.deepcopy(named_ranges)
    range_id = f"kix.{uuid.uuid4().hex[:12]}"

    if name not in named_ranges:
        named_ranges[name] = {
            "namedRangeId": range_id,
            "name": name,
            "namedRanges": [],
        }

    named_ranges[name]["namedRanges"].append({
        "namedRangeId": range_id,
        "name": name,
        "ranges": [{"startIndex": start, "endIndex": end, "segmentId": ""}],
    })

    return named_ranges, range_id


def delete_named_range(
    named_ranges: dict, named_range_id: str | None = None, name: str | None = None
) -> dict:
    """Delete a named range by ID or name. Returns new named_ranges."""
    named_ranges = copy.deepcopy(named_ranges)

    if name and name in named_ranges:
        del named_ranges[name]
    elif named_range_id:
        to_delete = None
        for n, nr in named_ranges.items():
            for sub in nr.get("namedRanges", []):
                if sub.get("namedRangeId") == named_range_id:
                    to_delete = n
                    break
            if to_delete:
                break
        if to_delete:
            del named_ranges[to_delete]

    return named_ranges


# ---------------------------------------------------------------------------
# Equations (Tier 3)
# ---------------------------------------------------------------------------

def insert_equation(body: dict, index: int) -> dict:
    """Insert an equation element at *index*. Returns new body.

    Equations in the real API are structural elements within paragraphs.
    They are essentially read-only in the API (created via UI), but we
    support inserting them for seed data.
    """
    body = copy.deepcopy(body)
    para_elem = find_paragraph_at_index(body, index)
    if not para_elem:
        return body

    para = para_elem["paragraph"]
    _split_text_run_at(para, index)

    new_elements: list[dict] = []
    inserted = False
    for pe in para.get("elements", []):
        si = pe.get("startIndex", 0)
        if not inserted and si >= index:
            new_elements.append({
                "startIndex": index,
                "endIndex": index + 1,
                "equation": {
                    "suggestedInsertionIds": [],
                    "suggestedDeletionIds": [],
                },
            })
            inserted = True
        new_elements.append(pe)

    if not inserted:
        new_elements.append({
            "startIndex": index,
            "endIndex": index + 1,
            "equation": {},
        })

    para["elements"] = new_elements
    return reindex_body(body)


# ---------------------------------------------------------------------------
# Positioned objects (Tier 3)
# ---------------------------------------------------------------------------

def insert_positioned_object(
    body: dict, positioned_objects: dict, paragraph_index: int,
    uri: str, size: dict | None = None, layout: str = "WRAP_TEXT"
) -> tuple[dict, dict, str]:
    """Add a positioned (floating) image anchored to a paragraph.

    Returns (body, positioned_objects, object_id).
    """
    positioned_objects = copy.deepcopy(positioned_objects)
    object_id = f"kix.{uuid.uuid4().hex[:12]}"

    positioned_objects[object_id] = {
        "objectId": object_id,
        "positionedObjectProperties": {
            "positioning": {
                "layout": layout,
                "leftOffset": {"magnitude": 0, "unit": "PT"},
                "topOffset": {"magnitude": 0, "unit": "PT"},
            },
            "embeddedObject": {
                "imageProperties": {
                    "contentUri": uri,
                    "sourceUri": uri,
                },
                "size": size or {
                    "width": {"magnitude": 200, "unit": "PT"},
                    "height": {"magnitude": 150, "unit": "PT"},
                },
            },
        },
    }

    # Link to paragraph via positionedObjectIds
    body = copy.deepcopy(body)
    para_elem = find_paragraph_at_index(body, paragraph_index)
    if para_elem:
        para = para_elem["paragraph"]
        if "positionedObjectIds" not in para:
            para["positionedObjectIds"] = []
        para["positionedObjectIds"].append(object_id)

    return body, positioned_objects, object_id


# ---------------------------------------------------------------------------
# Table of contents (Tier 3)
# ---------------------------------------------------------------------------

def insert_table_of_contents(body: dict, index: int) -> dict:
    """Insert a table of contents at *index*. Returns new body.

    The ToC is populated by scanning headings in the body.
    """
    body = copy.deepcopy(body)

    # Scan headings
    headings: list[dict] = []
    for elem in body.get("content", []):
        if "paragraph" in elem:
            pstyle = elem["paragraph"].get("paragraphStyle", {})
            nst = pstyle.get("namedStyleType", "")
            if nst.startswith("HEADING_"):
                heading_text = ""
                for pe in elem["paragraph"].get("elements", []):
                    if "textRun" in pe:
                        heading_text += pe["textRun"].get("content", "")
                headings.append({
                    "text": heading_text.strip(),
                    "level": nst,
                    "startIndex": elem.get("startIndex", 0),
                })

    # Build ToC content as paragraphs with links
    toc_content: list[dict] = []
    for heading in headings:
        toc_content.append({
            "startIndex": 0,
            "endIndex": 0,
            "paragraph": {
                "elements": [{
                    "startIndex": 0,
                    "endIndex": 0,
                    "textRun": {
                        "content": heading["text"] + "\n",
                        "textStyle": {
                            "link": {"headingId": f"h.{heading['startIndex']}"},
                        },
                    },
                }],
                "paragraphStyle": {
                    "namedStyleType": "NORMAL_TEXT",
                    "direction": "LEFT_TO_RIGHT",
                },
            },
        })

    if not toc_content:
        toc_content = [{
            "startIndex": 0,
            "endIndex": 0,
            "paragraph": {
                "elements": [{"startIndex": 0, "endIndex": 0, "textRun": {"content": "\n", "textStyle": {}}}],
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT", "direction": "LEFT_TO_RIGHT"},
            },
        }]

    toc_elem = {
        "startIndex": index,
        "endIndex": index,
        "tableOfContents": {"content": toc_content},
    }

    # Insert at index (split paragraph if needed)
    content = body.get("content", [])
    new_content: list[dict] = []
    inserted = False

    for elem in content:
        if inserted:
            new_content.append(elem)
            continue

        si = elem.get("startIndex", 0)
        ei = elem.get("endIndex", 0)

        if "paragraph" in elem and si <= index <= ei:
            before, after = _split_paragraph_at_index(elem, index)
            if before:
                new_content.append(before)
            new_content.append(toc_elem)
            if after:
                new_content.append(after)
            else:
                new_content.append({
                    "startIndex": 0, "endIndex": 0,
                    "paragraph": {
                        "elements": [{"startIndex": 0, "endIndex": 0, "textRun": {"content": "\n", "textStyle": {}}}],
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT", "direction": "LEFT_TO_RIGHT"},
                    },
                })
            inserted = True
        elif si >= index and not inserted:
            new_content.append(toc_elem)
            new_content.append(elem)
            inserted = True
        else:
            new_content.append(elem)

    if not inserted:
        new_content.append(toc_elem)

    body["content"] = new_content
    return reindex_body(body)


# ---------------------------------------------------------------------------
# Document style update
# ---------------------------------------------------------------------------

def update_document_style(doc_style: dict, new_style: dict, fields: str) -> dict:
    """Merge *new_style* into *doc_style* for the named *fields*."""
    doc_style = copy.deepcopy(doc_style)
    field_list = [f.strip() for f in fields.split(",") if f.strip()]
    for field in field_list:
        if field in new_style:
            doc_style[field] = copy.deepcopy(new_style[field])
    return doc_style


# ---------------------------------------------------------------------------
# deletePositionedObject
# ---------------------------------------------------------------------------

def delete_positioned_object(
    body: dict, positioned_objects: dict, object_id: str
) -> tuple[dict, dict]:
    """Remove a positioned (floating) object by ID.

    Returns (body, positioned_objects).
    """
    body = copy.deepcopy(body)
    positioned_objects = copy.deepcopy(positioned_objects)
    positioned_objects.pop(object_id, None)

    # Remove references from paragraphs
    for elem in body.get("content", []):
        if "paragraph" in elem:
            ids = elem["paragraph"].get("positionedObjectIds", [])
            if object_id in ids:
                ids.remove(object_id)
                if not ids:
                    del elem["paragraph"]["positionedObjectIds"]

    return body, positioned_objects


# ---------------------------------------------------------------------------
# replaceImage
# ---------------------------------------------------------------------------

def replace_image(
    inline_objects: dict, positioned_objects: dict,
    image_object_id: str, new_uri: str
) -> tuple[dict, dict]:
    """Replace an existing image (inline or positioned) with a new URI.

    Returns (inline_objects, positioned_objects).
    """
    inline_objects = copy.deepcopy(inline_objects)
    positioned_objects = copy.deepcopy(positioned_objects)

    if image_object_id in inline_objects:
        eo = inline_objects[image_object_id].get(
            "inlineObjectProperties", {}
        ).get("embeddedObject", {})
        ip = eo.get("imageProperties", {})
        ip["contentUri"] = new_uri
        ip["sourceUri"] = new_uri

    if image_object_id in positioned_objects:
        eo = positioned_objects[image_object_id].get(
            "positionedObjectProperties", {}
        ).get("embeddedObject", {})
        ip = eo.get("imageProperties", {})
        ip["contentUri"] = new_uri
        ip["sourceUri"] = new_uri

    return inline_objects, positioned_objects


# ---------------------------------------------------------------------------
# replaceNamedRangeContent
# ---------------------------------------------------------------------------

def replace_named_range_content(
    body: dict, named_ranges: dict, text: str,
    named_range_id: str | None = None, named_range_name: str | None = None
) -> dict:
    """Replace all content within a named range with *text*.

    Finds the range(s) for the named range, deletes their content, and
    inserts *text* at the start of each range. Returns new body.
    """
    # Find the named range entry
    nr_entry = None
    if named_range_name and named_range_name in named_ranges:
        nr_entry = named_ranges[named_range_name]
    elif named_range_id:
        for _name, nr in named_ranges.items():
            for sub in nr.get("namedRanges", []):
                if sub.get("namedRangeId") == named_range_id:
                    nr_entry = nr
                    break
            if nr_entry:
                break

    if not nr_entry:
        return body

    # Collect all ranges (process in reverse order to avoid index shifting)
    all_ranges: list[dict] = []
    for sub in nr_entry.get("namedRanges", []):
        all_ranges.extend(sub.get("ranges", []))

    all_ranges.sort(key=lambda r: r.get("startIndex", 0), reverse=True)

    for r in all_ranges:
        start = r.get("startIndex", 0)
        end = r.get("endIndex", 0)
        if start < end:
            body = delete_range(body, start, end)
            if text:
                body = insert_text(body, start, text)

    return body


# ---------------------------------------------------------------------------
# updateSectionStyle
# ---------------------------------------------------------------------------

def update_section_style(
    body: dict, start: int, end: int, style: dict, fields: str
) -> dict:
    """Update sectionStyle for section breaks overlapping [start, end)."""
    body = copy.deepcopy(body)
    for elem in body.get("content", []):
        if "sectionBreak" not in elem:
            continue
        ei = elem.get("endIndex", 0)
        # Section break at index <= start applies to the section containing [start, end)
        if ei <= end:
            ss = elem["sectionBreak"].get("sectionStyle", {})
            field_list = [f.strip() for f in fields.split(",") if f.strip()]
            for field in field_list:
                if field in style:
                    ss[field] = copy.deepcopy(style[field])
            elem["sectionBreak"]["sectionStyle"] = ss
    return body


# ---------------------------------------------------------------------------
# pinTableHeaderRows
# ---------------------------------------------------------------------------

def pin_table_header_rows(
    body: dict, table_start_index: int, pinned_rows: int
) -> dict:
    """Set the number of pinned header rows for a table."""
    body = copy.deepcopy(body)
    table_elem = _find_table_at_index(body, table_start_index)
    if not table_elem:
        return body

    table = table_elem["table"]
    if "tableStyle" not in table:
        table["tableStyle"] = {}
    table["tableStyle"]["pinnedHeaderRowsCount"] = pinned_rows
    return body


# ---------------------------------------------------------------------------
# Tabs (addDocumentTab, deleteTab, updateDocumentTabProperties)
# ---------------------------------------------------------------------------

def add_document_tab(tabs: list[dict], tab_properties: dict) -> tuple[list[dict], str]:
    """Add a new document tab. Returns (tabs, tab_id)."""
    tabs = copy.deepcopy(tabs)
    tab_id = f"t.{len(tabs)}"
    new_tab = {
        "tabProperties": {
            "tabId": tab_id,
            "title": tab_properties.get("title", f"Tab {len(tabs) + 1}"),
            "index": tab_properties.get("index", len(tabs)),
        },
        "documentTab": {
            "body": {
                "content": [
                    {
                        "endIndex": 1,
                        "sectionBreak": {
                            "sectionStyle": {
                                "columnSeparatorStyle": "NONE",
                                "contentDirection": "LEFT_TO_RIGHT",
                                "sectionType": "CONTINUOUS",
                            }
                        },
                    },
                    {
                        "startIndex": 1,
                        "endIndex": 2,
                        "paragraph": {
                            "elements": [{
                                "startIndex": 1,
                                "endIndex": 2,
                                "textRun": {"content": "\n", "textStyle": {}},
                            }],
                            "paragraphStyle": {
                                "namedStyleType": "NORMAL_TEXT",
                                "direction": "LEFT_TO_RIGHT",
                            },
                        },
                    },
                ]
            }
        },
    }
    tabs.append(new_tab)
    return tabs, tab_id


def delete_tab(tabs: list[dict], tab_id: str) -> list[dict]:
    """Delete a document tab by ID. Returns updated tabs."""
    return [t for t in tabs if t.get("tabProperties", {}).get("tabId") != tab_id]


def update_document_tab_properties(
    tabs: list[dict], tab_id: str, properties: dict, fields: str
) -> list[dict]:
    """Update properties for a document tab. Returns updated tabs."""
    tabs = copy.deepcopy(tabs)
    for tab in tabs:
        if tab.get("tabProperties", {}).get("tabId") == tab_id:
            field_list = [f.strip() for f in fields.split(",") if f.strip()]
            for field in field_list:
                if field in properties:
                    tab["tabProperties"][field] = properties[field]
            break
    return tabs


# ---------------------------------------------------------------------------
# insertPerson (@ mentions)
# ---------------------------------------------------------------------------

def insert_person(
    body: dict, index: int, person_id: str, name: str = ""
) -> dict:
    """Insert a person mention at *index*. Returns new body.

    A person chip occupies 1 index, similar to an inlineObjectElement.
    """
    body = copy.deepcopy(body)
    para_elem = find_paragraph_at_index(body, index)
    if not para_elem:
        return body

    para = para_elem["paragraph"]
    _split_text_run_at(para, index)

    new_elements: list[dict] = []
    inserted = False
    for pe in para.get("elements", []):
        si = pe.get("startIndex", 0)
        if not inserted and si >= index:
            new_elements.append({
                "startIndex": index,
                "endIndex": index + 1,
                "person": {
                    "personId": person_id,
                    "personProperties": {
                        "email": person_id,
                        "name": name or person_id,
                    },
                    "textStyle": {
                        "foregroundColor": {
                            "color": {"rgbColor": {"red": 0.06, "green": 0.46, "blue": 0.87}}
                        },
                        "link": {"url": f"mailto:{person_id}"},
                    },
                },
            })
            inserted = True
        new_elements.append(pe)

    if not inserted:
        new_elements.append({
            "startIndex": index,
            "endIndex": index + 1,
            "person": {
                "personId": person_id,
                "personProperties": {"email": person_id, "name": name or person_id},
                "textStyle": {},
            },
        })

    para["elements"] = new_elements
    return reindex_body(body)
