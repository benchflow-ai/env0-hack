"""Documents API endpoints — Google Docs REST API v1."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from mock_gdoc.models import Document, DocumentRevision
from mock_gdoc.seed.body_builder import (
    create_empty_body,
    create_default_document_style,
    create_default_named_styles,
)
from mock_gdoc import body_ops
from .deps import get_db, resolve_user_id, check_document_access, check_write_access
from .schemas import (
    DocumentSchema,
    DocumentCreateRequest,
    BatchUpdateDocumentRequest,
    BatchUpdateDocumentResponse,
    WriteControl,
    Body,
)

router = APIRouter()


def _nonempty(d: dict) -> dict | None:
    """Return *d* if non-empty, else None (so exclude_none omits it)."""
    return d if d else None


def _document_to_schema(doc: Document) -> dict:
    """Convert a Document model to its API-compatible dict.

    Empty dicts ({}) are omitted, matching the real Google API which
    only returns non-empty top-level maps.
    """
    body_dict = doc.body
    schema = DocumentSchema(
        documentId=doc.id,
        title=doc.title,
        body=Body(**body_dict) if body_dict else Body(content=[]),
        revisionId=doc.revision_id,
        suggestionsViewMode=doc.suggestions_view_mode,
        documentStyle=_nonempty(doc.document_style),
        namedStyles=_nonempty(doc.named_styles),
        lists=_nonempty(doc.lists),
        inlineObjects=_nonempty(doc.inline_objects),
        headers=_nonempty(doc.headers),
        footers=_nonempty(doc.footers),
        footnotes=_nonempty(doc.footnotes),
        namedRanges=_nonempty(doc.named_ranges),
        positionedObjects=_nonempty(doc.positioned_objects),
    )
    return schema.model_dump(exclude_none=True)


@router.get("/documents/{documentId}", tags=["documents"])
def get_document(
    documentId: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """Get a document by ID."""
    doc = check_document_access(db, documentId, user_id)
    return _document_to_schema(doc)


@router.post("/documents", tags=["documents"])
def create_document(
    request: DocumentCreateRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """Create a new document."""
    doc_id = str(uuid.uuid4()).replace("-", "")[:44]
    rev_id = str(uuid.uuid4()).replace("-", "")[:8]
    now = datetime.now(timezone.utc)

    doc = Document(
        id=doc_id,
        title=request.title,
        revision_id=rev_id,
        user_id=user_id,
        created_time=now,
        modified_time=now,
    )
    doc.body = create_empty_body()
    doc.document_style = create_default_document_style()
    doc.named_styles = create_default_named_styles()

    db.add(doc)

    # Create initial revision
    db.add(DocumentRevision(
        id=f"rev_{rev_id}",
        document_id=doc_id,
        user_id=user_id,
        modified_time=now,
    ))

    db.commit()
    db.refresh(doc)
    return _document_to_schema(doc)


@router.post(
    "/documents/{documentId}:batchUpdate",
    response_model=BatchUpdateDocumentResponse,
    tags=["documents"],
)
def batch_update_document(
    documentId: str,
    request: BatchUpdateDocumentRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """Apply a batch of updates to a document."""
    doc = check_write_access(db, documentId, user_id)

    body = doc.body
    lists_map = doc.lists
    inline_objects_map = doc.inline_objects
    headers_map = doc.headers
    footers_map = doc.footers
    footnotes_map = doc.footnotes
    named_ranges_map = doc.named_ranges
    positioned_objects_map = doc.positioned_objects
    doc_style = doc.document_style
    tabs_list = doc.tabs

    replies: list[dict] = []

    for req in request.requests:
        reply: dict = {}

        for req_type, handler in _HANDLERS.items():
            if req_type in req:
                result = handler(
                    req[req_type],
                    body=body,
                    lists=lists_map,
                    inline_objects=inline_objects_map,
                    headers=headers_map,
                    footers=footers_map,
                    footnotes=footnotes_map,
                    named_ranges=named_ranges_map,
                    positioned_objects=positioned_objects_map,
                    doc_style=doc_style,
                    tabs=tabs_list,
                )
                # Unpack result
                body = result.get("body", body)
                lists_map = result.get("lists", lists_map)
                inline_objects_map = result.get("inline_objects", inline_objects_map)
                headers_map = result.get("headers", headers_map)
                footers_map = result.get("footers", footers_map)
                footnotes_map = result.get("footnotes", footnotes_map)
                named_ranges_map = result.get("named_ranges", named_ranges_map)
                positioned_objects_map = result.get("positioned_objects", positioned_objects_map)
                doc_style = result.get("doc_style", doc_style)
                tabs_list = result.get("tabs", tabs_list)
                reply = result.get("reply", {})
                break

        replies.append(reply)

    # Persist all changes
    doc.body = body
    doc.lists = lists_map
    doc.inline_objects = inline_objects_map
    doc.headers = headers_map
    doc.footers = footers_map
    doc.footnotes = footnotes_map
    doc.named_ranges = named_ranges_map
    doc.positioned_objects = positioned_objects_map
    doc.document_style = doc_style
    doc.tabs = tabs_list
    doc.modified_time = datetime.now(timezone.utc)

    # Bump revision
    new_rev_id = str(uuid.uuid4()).replace("-", "")[:8]
    doc.revision_id = new_rev_id
    db.add(DocumentRevision(
        id=f"rev_{new_rev_id}",
        document_id=documentId,
        user_id=user_id,
        modified_time=doc.modified_time,
    ))

    db.commit()
    return BatchUpdateDocumentResponse(
        documentId=documentId,
        replies=replies,
        writeControl=WriteControl(requiredRevisionId=new_rev_id),
    )


# ---------------------------------------------------------------------------
# batchUpdate request handlers
# ---------------------------------------------------------------------------
# Each handler receives the request payload and keyword args for all mutable
# state. Returns a dict with updated state and optional "reply".
# ---------------------------------------------------------------------------

def _handle_insert_text(payload, *, body, **kw):
    index = payload.get("location", {}).get("index", 1)
    text = payload.get("text", "")
    return {"body": body_ops.insert_text(body, index, text)}


def _handle_delete_content_range(payload, *, body, **kw):
    r = payload.get("range", {})
    start = r.get("startIndex", 1)
    end = r.get("endIndex", 1)
    return {"body": body_ops.delete_range(body, start, end)}


def _handle_replace_all_text(payload, *, body, **kw):
    ct = payload.get("containsText", {})
    search = ct.get("text", "")
    match_case = ct.get("matchCase", True)
    replace = payload.get("replaceText", "")
    new_body, count = body_ops.replace_all_text(body, search, replace, match_case)
    return {
        "body": new_body,
        "reply": {"replaceAllText": {"occurrencesChanged": count}},
    }


# --- Tier 1: Text & Paragraph styles ---

def _handle_update_text_style(payload, *, body, **kw):
    r = payload.get("range", {})
    start = r.get("startIndex", 0)
    end = r.get("endIndex", 0)
    style = payload.get("textStyle", {})
    fields = payload.get("fields", "*")
    return {"body": body_ops.apply_text_style(body, start, end, style, fields)}


def _handle_update_paragraph_style(payload, *, body, **kw):
    r = payload.get("range", {})
    start = r.get("startIndex", 0)
    end = r.get("endIndex", 0)
    style = payload.get("paragraphStyle", {})
    fields = payload.get("fields", "*")
    return {"body": body_ops.apply_paragraph_style(body, start, end, style, fields)}


# --- Tier 1: Lists ---

def _handle_create_paragraph_bullets(payload, *, body, lists, **kw):
    r = payload.get("range", {})
    start = r.get("startIndex", 0)
    end = r.get("endIndex", 0)
    preset = payload.get("bulletPreset", "BULLET_DISC_CIRCLE_SQUARE")
    new_body, new_lists = body_ops.create_paragraph_bullets(
        body, lists, start, end, preset
    )
    return {"body": new_body, "lists": new_lists}


def _handle_delete_paragraph_bullets(payload, *, body, lists, **kw):
    r = payload.get("range", {})
    start = r.get("startIndex", 0)
    end = r.get("endIndex", 0)
    new_body, new_lists = body_ops.delete_paragraph_bullets(body, lists, start, end)
    return {"body": new_body, "lists": new_lists}


# --- Tier 1: Tables ---

def _handle_insert_table(payload, *, body, **kw):
    index = payload.get("location", {}).get("index", 1)
    rows = payload.get("rows", 1)
    cols = payload.get("columns", 1)
    return {"body": body_ops.insert_table(body, index, rows, cols)}


def _handle_insert_table_row(payload, *, body, **kw):
    loc = payload.get("tableCellLocation", {})
    table_start = loc.get("tableStartLocation", {}).get("index", 0)
    row_index = loc.get("rowIndex", 0)
    insert_below = payload.get("insertBelow", True)
    return {"body": body_ops.insert_table_row(body, table_start, row_index, insert_below)}


def _handle_insert_table_column(payload, *, body, **kw):
    loc = payload.get("tableCellLocation", {})
    table_start = loc.get("tableStartLocation", {}).get("index", 0)
    col_index = loc.get("columnIndex", 0)
    insert_right = payload.get("insertRight", True)
    return {"body": body_ops.insert_table_column(body, table_start, col_index, insert_right)}


def _handle_delete_table_row(payload, *, body, **kw):
    loc = payload.get("tableCellLocation", {})
    table_start = loc.get("tableStartLocation", {}).get("index", 0)
    row_index = loc.get("rowIndex", 0)
    return {"body": body_ops.delete_table_row(body, table_start, row_index)}


def _handle_delete_table_column(payload, *, body, **kw):
    loc = payload.get("tableCellLocation", {})
    table_start = loc.get("tableStartLocation", {}).get("index", 0)
    col_index = loc.get("columnIndex", 0)
    return {"body": body_ops.delete_table_column(body, table_start, col_index)}


def _handle_merge_table_cells(payload, *, body, **kw):
    tr = payload.get("tableRange", {})
    loc = tr.get("tableCellLocation", {})
    table_start = loc.get("tableStartLocation", {}).get("index", 0)
    row_index = loc.get("rowIndex", 0)
    col_index = loc.get("columnIndex", 0)
    row_span = tr.get("rowSpan", 1)
    col_span = tr.get("columnSpan", 1)
    return {"body": body_ops.merge_table_cells(
        body, table_start, row_index, col_index, row_span, col_span
    )}


def _handle_unmerge_table_cells(payload, *, body, **kw):
    tr = payload.get("tableRange", {})
    loc = tr.get("tableCellLocation", {})
    table_start = loc.get("tableStartLocation", {}).get("index", 0)
    row_index = loc.get("rowIndex", 0)
    col_index = loc.get("columnIndex", 0)
    row_span = tr.get("rowSpan", 1)
    col_span = tr.get("columnSpan", 1)
    return {"body": body_ops.unmerge_table_cells(
        body, table_start, row_index, col_index, row_span, col_span
    )}


def _handle_update_table_cell_style(payload, *, body, **kw):
    tr = payload.get("tableRange", {})
    loc = tr.get("tableCellLocation", {})
    table_start = loc.get("tableStartLocation", {}).get("index", 0)
    row_index = loc.get("rowIndex", 0)
    col_index = loc.get("columnIndex", 0)
    row_span = tr.get("rowSpan", 1)
    col_span = tr.get("columnSpan", 1)
    style = payload.get("tableCellStyle", {})
    fields = payload.get("fields", "*")
    return {"body": body_ops.update_table_cell_style(
        body, table_start, row_index, col_index, row_span, col_span, style, fields
    )}


def _handle_update_table_column_properties(payload, *, body, **kw):
    table_start = payload.get("tableStartLocation", {}).get("index", 0)
    col_indices = payload.get("columnIndices", [])
    properties = payload.get("tableColumnProperties", {})
    fields = payload.get("fields", "*")
    return {"body": body_ops.update_table_column_properties(
        body, table_start, col_indices, properties, fields
    )}


def _handle_update_table_row_style(payload, *, body, **kw):
    table_start = payload.get("tableStartLocation", {}).get("index", 0)
    row_indices = payload.get("rowIndices", [])
    style = payload.get("tableRowStyle", {})
    fields = payload.get("fields", "*")
    return {"body": body_ops.update_table_row_style(
        body, table_start, row_indices, style, fields
    )}


# --- Tier 1: Document & Named styles ---

def _handle_update_document_style(payload, *, doc_style, **kw):
    style = payload.get("documentStyle", {})
    fields = payload.get("fields", "*")
    return {"doc_style": body_ops.update_document_style(doc_style, style, fields)}


# --- Tier 2: Inline images ---

def _handle_insert_inline_image(payload, *, body, inline_objects, **kw):
    index = payload.get("location", {}).get("index", 1)
    uri = payload.get("uri", "")
    size = payload.get("objectSize", None)
    new_body, new_io, obj_id = body_ops.insert_inline_image(
        body, inline_objects, index, uri, size
    )
    return {
        "body": new_body,
        "inline_objects": new_io,
        "reply": {"insertInlineImage": {"objectId": obj_id}},
    }


# --- Tier 2: Page break ---

def _handle_insert_page_break(payload, *, body, **kw):
    index = payload.get("location", {}).get("index", 1)
    return {"body": body_ops.insert_page_break(body, index)}


# --- Tier 2: Section break ---

def _handle_insert_section_break(payload, *, body, **kw):
    index = payload.get("location", {}).get("index", 1)
    section_type = payload.get("sectionType", "CONTINUOUS")
    return {"body": body_ops.insert_section_break(body, index, section_type)}


# --- Tier 2: Headers & Footers ---

def _handle_create_header(payload, *, body, headers, **kw):
    header_type = payload.get("type", "DEFAULT")
    new_body, new_headers, header_id = body_ops.create_header(
        body, headers, header_type
    )
    return {
        "body": new_body,
        "headers": new_headers,
        "reply": {"createHeader": {"headerId": header_id}},
    }


def _handle_create_footer(payload, *, body, footers, **kw):
    footer_type = payload.get("type", "DEFAULT")
    new_body, new_footers, footer_id = body_ops.create_footer(
        body, footers, footer_type
    )
    return {
        "body": new_body,
        "footers": new_footers,
        "reply": {"createFooter": {"footerId": footer_id}},
    }


def _handle_delete_header(payload, *, body, headers, **kw):
    header_id = payload.get("headerId", "")
    new_body, new_headers = body_ops.delete_header(body, headers, header_id)
    return {"body": new_body, "headers": new_headers}


def _handle_delete_footer(payload, *, body, footers, **kw):
    footer_id = payload.get("footerId", "")
    new_body, new_footers = body_ops.delete_footer(body, footers, footer_id)
    return {"body": new_body, "footers": new_footers}


# --- Tier 2: Footnotes ---

def _handle_create_footnote(payload, *, body, footnotes, **kw):
    index = payload.get("location", {}).get("index", 1)
    new_body, new_fn, fn_id = body_ops.create_footnote(body, footnotes, index)
    return {
        "body": new_body,
        "footnotes": new_fn,
        "reply": {"createFootnote": {"footnoteId": fn_id}},
    }


# --- Tier 2: Named ranges ---

def _handle_create_named_range(payload, *, named_ranges, **kw):
    name = payload.get("name", "")
    r = payload.get("range", {})
    start = r.get("startIndex", 0)
    end = r.get("endIndex", 0)
    new_nr, range_id = body_ops.create_named_range(named_ranges, name, start, end)
    return {
        "named_ranges": new_nr,
        "reply": {"createNamedRange": {"namedRangeId": range_id}},
    }


def _handle_delete_named_range(payload, *, named_ranges, **kw):
    range_id = payload.get("namedRangeId")
    name = payload.get("name")
    return {"named_ranges": body_ops.delete_named_range(named_ranges, range_id, name)}


# --- Tier 3: Equations ---

def _handle_insert_equation(payload, *, body, **kw):
    index = payload.get("location", {}).get("index", 1)
    return {"body": body_ops.insert_equation(body, index)}


# --- Tier 3: Table of contents ---

def _handle_insert_table_of_contents(payload, *, body, **kw):
    index = payload.get("location", {}).get("index", 1)
    return {"body": body_ops.insert_table_of_contents(body, index)}


# --- Tier 3: Positioned objects ---

def _handle_insert_positioned_object(payload, *, body, positioned_objects, **kw):
    para_index = payload.get("location", {}).get("index", 1)
    uri = payload.get("uri", "")
    size = payload.get("objectSize", None)
    layout = payload.get("layout", "WRAP_TEXT")
    new_body, new_po, obj_id = body_ops.insert_positioned_object(
        body, positioned_objects, para_index, uri, size, layout
    )
    return {
        "body": new_body,
        "positioned_objects": new_po,
        "reply": {"insertPositionedObject": {"objectId": obj_id}},
    }


def _handle_delete_positioned_object(payload, *, body, positioned_objects, **kw):
    object_id = payload.get("objectId", "")
    new_body, new_po = body_ops.delete_positioned_object(body, positioned_objects, object_id)
    return {"body": new_body, "positioned_objects": new_po}


# --- replaceImage ---

def _handle_replace_image(payload, *, inline_objects, positioned_objects, **kw):
    image_id = payload.get("imageObjectId", "")
    uri = payload.get("uri", "")
    new_io, new_po = body_ops.replace_image(inline_objects, positioned_objects, image_id, uri)
    return {"inline_objects": new_io, "positioned_objects": new_po}


# --- replaceNamedRangeContent ---

def _handle_replace_named_range_content(payload, *, body, named_ranges, **kw):
    text = payload.get("text", "")
    nr_id = payload.get("namedRangeId")
    nr_name = payload.get("namedRangeName")
    new_body = body_ops.replace_named_range_content(
        body, named_ranges, text, nr_id, nr_name
    )
    return {"body": new_body}


# --- updateSectionStyle ---

def _handle_update_section_style(payload, *, body, **kw):
    r = payload.get("range", {})
    start = r.get("startIndex", 0)
    end = r.get("endIndex", 0)
    style = payload.get("sectionStyle", {})
    fields = payload.get("fields", "*")
    return {"body": body_ops.update_section_style(body, start, end, style, fields)}


# --- pinTableHeaderRows ---

def _handle_pin_table_header_rows(payload, *, body, **kw):
    table_start = payload.get("tableStartLocation", {}).get("index", 0)
    pinned = payload.get("pinnedHeaderRowsCount", 0)
    return {"body": body_ops.pin_table_header_rows(body, table_start, pinned)}


# --- Tabs ---

def _handle_add_document_tab(payload, *, tabs, **kw):
    props = payload.get("tabProperties", {})
    new_tabs, tab_id = body_ops.add_document_tab(tabs, props)
    return {"tabs": new_tabs, "reply": {"addDocumentTab": {"tabId": tab_id}}}


def _handle_delete_tab(payload, *, tabs, **kw):
    tab_id = payload.get("tabId", "")
    return {"tabs": body_ops.delete_tab(tabs, tab_id)}


def _handle_update_document_tab_properties(payload, *, tabs, **kw):
    tab_id = payload.get("tabProperties", {}).get("tabId", "")
    props = payload.get("tabProperties", {})
    fields = payload.get("fields", "*")
    return {"tabs": body_ops.update_document_tab_properties(tabs, tab_id, props, fields)}


# --- insertPerson ---

def _handle_insert_person(payload, *, body, **kw):
    index = payload.get("location", {}).get("index", 1)
    person_props = payload.get("personProperties", {})
    person_id = person_props.get("email", "")
    name = person_props.get("name", "")
    return {"body": body_ops.insert_person(body, index, person_id, name)}


# ---------------------------------------------------------------------------
# Handler dispatch table — real Google Docs API batchUpdate request types
# ---------------------------------------------------------------------------

_HANDLERS = {
    # Text editing
    "insertText": _handle_insert_text,
    "deleteContentRange": _handle_delete_content_range,
    "replaceAllText": _handle_replace_all_text,
    # Character formatting
    "updateTextStyle": _handle_update_text_style,
    # Paragraph formatting
    "updateParagraphStyle": _handle_update_paragraph_style,
    "createParagraphBullets": _handle_create_paragraph_bullets,
    "deleteParagraphBullets": _handle_delete_paragraph_bullets,
    # Tables
    "insertTable": _handle_insert_table,
    "insertTableRow": _handle_insert_table_row,
    "insertTableColumn": _handle_insert_table_column,
    "deleteTableRow": _handle_delete_table_row,
    "deleteTableColumn": _handle_delete_table_column,
    "mergeTableCells": _handle_merge_table_cells,
    "unmergeTableCells": _handle_unmerge_table_cells,
    "updateTableCellStyle": _handle_update_table_cell_style,
    "updateTableColumnProperties": _handle_update_table_column_properties,
    "updateTableRowStyle": _handle_update_table_row_style,
    "pinTableHeaderRows": _handle_pin_table_header_rows,
    # Images and media
    "insertInlineImage": _handle_insert_inline_image,
    "replaceImage": _handle_replace_image,
    "deletePositionedObject": _handle_delete_positioned_object,
    "insertPerson": _handle_insert_person,
    # Document structure/layout
    "insertPageBreak": _handle_insert_page_break,
    "insertSectionBreak": _handle_insert_section_break,
    "updateSectionStyle": _handle_update_section_style,
    "updateDocumentStyle": _handle_update_document_style,
    "createHeader": _handle_create_header,
    "createFooter": _handle_create_footer,
    "deleteHeader": _handle_delete_header,
    "deleteFooter": _handle_delete_footer,
    "createFootnote": _handle_create_footnote,
    # Named ranges
    "createNamedRange": _handle_create_named_range,
    "deleteNamedRange": _handle_delete_named_range,
    "replaceNamedRangeContent": _handle_replace_named_range_content,
    # Tabs
    "addDocumentTab": _handle_add_document_tab,
    "deleteTab": _handle_delete_tab,
    "updateDocumentTabProperties": _handle_update_document_tab_properties,
}
