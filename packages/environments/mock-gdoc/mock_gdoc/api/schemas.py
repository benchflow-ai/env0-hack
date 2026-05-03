"""Pydantic schemas for Google Docs API responses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# --- Text style ---
class TextStyle(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    strikethrough: bool | None = None
    fontSize: dict | None = None  # {"magnitude": 12, "unit": "PT"}
    foregroundColor: dict | None = None
    backgroundColor: dict | None = None
    link: dict | None = None  # {"url": "..."} or {"headingId": "..."}
    baselineOffset: str | None = None
    smallCaps: bool | None = None
    weightedFontFamily: dict | None = None


class ParagraphStyle(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    namedStyleType: str | None = None  # NORMAL_TEXT, HEADING_1, etc.
    alignment: str | None = None  # START, CENTER, END, JUSTIFIED
    lineSpacing: float | None = None
    direction: str | None = None
    spacingMode: str | None = None  # COLLAPSE_LISTS, NEVER_COLLAPSE
    spaceAbove: dict | None = None
    spaceBelow: dict | None = None
    indentFirstLine: dict | None = None
    indentStart: dict | None = None
    indentEnd: dict | None = None
    keepLinesTogether: bool | None = None
    keepWithNext: bool | None = None
    avoidWidowAndOrphan: bool | None = None
    pageBreakBefore: bool | None = None
    shading: dict | None = None
    borderTop: dict | None = None
    borderBottom: dict | None = None
    borderLeft: dict | None = None
    borderRight: dict | None = None
    borderBetween: dict | None = None
    headingId: str | None = None


# --- Bullet ---
class Bullet(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    listId: str
    nestingLevel: int = 0
    textStyle: TextStyle | None = None


# --- Paragraph elements ---
class TextRun(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    content: str = ""
    textStyle: TextStyle | None = None


class InlineObjectElement(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    inlineObjectId: str
    textStyle: TextStyle | None = None


class PageBreak(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    textStyle: TextStyle | None = None


class FootnoteReference(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    footnoteId: str
    footnoteNumber: str | None = None
    textStyle: TextStyle | None = None


class Equation(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    suggestedInsertionIds: list[str] | None = None
    suggestedDeletionIds: list[str] | None = None


class PersonProperties(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    email: str | None = None
    name: str | None = None


class Person(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    personId: str | None = None
    personProperties: PersonProperties | None = None
    textStyle: TextStyle | None = None


class ParagraphElement(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    startIndex: int | None = None
    endIndex: int | None = None
    textRun: TextRun | None = None
    inlineObjectElement: InlineObjectElement | None = None
    pageBreak: PageBreak | None = None
    footnoteReference: FootnoteReference | None = None
    equation: Equation | None = None
    person: Person | None = None


class Paragraph(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    elements: list[ParagraphElement] = []
    paragraphStyle: ParagraphStyle | None = None
    bullet: Bullet | None = None
    positionedObjectIds: list[str] | None = None


class SectionBreak(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    sectionStyle: dict | None = None


class TableCell(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    startIndex: int | None = None
    endIndex: int | None = None
    content: list[StructuralElement] = []
    tableCellStyle: dict | None = None


class TableRow(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    startIndex: int | None = None
    endIndex: int | None = None
    tableCells: list[TableCell] = []
    tableRowStyle: dict | None = None


class Table(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    rows: int = 0
    columns: int = 0
    tableRows: list[TableRow] = []
    tableStyle: dict | None = None


class TableOfContents(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    content: list[StructuralElement] = []


# --- Structural elements ---
class StructuralElement(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    startIndex: int | None = None
    endIndex: int | None = None
    paragraph: Paragraph | None = None
    sectionBreak: SectionBreak | None = None
    table: Table | None = None
    tableOfContents: TableOfContents | None = None


# Fix forward references
TableCell.model_rebuild()
TableOfContents.model_rebuild()


# --- Body ---
class Body(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    content: list[StructuralElement] = []


# --- Lists ---
class NestingLevel(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    bulletAlignment: str | None = None
    glyphType: str | None = None
    glyphFormat: str | None = None
    glyphSymbol: str | None = None
    indentFirstLine: dict | None = None
    indentStart: dict | None = None
    startNumber: int | None = None
    textStyle: TextStyle | None = None


class ListProperties(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    nestingLevels: list[NestingLevel] = []


class ListInfo(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    listProperties: ListProperties | None = None


# --- Inline objects ---
class EmbeddedObject(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    imageProperties: dict | None = None
    size: dict | None = None
    embeddedObjectBorder: dict | None = None
    title: str | None = None
    description: str | None = None


class InlineObjectProperties(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    embeddedObject: EmbeddedObject | None = None


class InlineObject(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    objectId: str
    inlineObjectProperties: InlineObjectProperties | None = None


# --- Headers & Footers ---
class Header(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    headerId: str
    content: list[StructuralElement] = []


class Footer(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    footerId: str
    content: list[StructuralElement] = []


# --- Footnotes ---
class Footnote(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    footnoteId: str
    content: list[StructuralElement] = []


# --- Named ranges ---
class NamedRangeEntry(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    namedRangeId: str
    name: str
    ranges: list[dict] = []


class NamedRanges(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    namedRangeId: str
    name: str
    namedRanges: list[NamedRangeEntry] = []


# --- Positioned objects ---
class PositionedObjectProperties(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    positioning: dict | None = None
    embeddedObject: EmbeddedObject | None = None


class PositionedObject(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    objectId: str
    positionedObjectProperties: PositionedObjectProperties | None = None


# --- Document ---
class DocumentSchema(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    documentId: str
    title: str = ""
    body: Body | None = None
    revisionId: str = "1"
    suggestionsViewMode: str | None = None
    documentStyle: dict | None = None
    namedStyles: dict | None = None
    lists: dict | None = None
    inlineObjects: dict | None = None
    headers: dict | None = None
    footers: dict | None = None
    footnotes: dict | None = None
    namedRanges: dict | None = None
    positionedObjects: dict | None = None


class DocumentListSchema(BaseModel):
    documents: list[DocumentSchema] = []
    count: int = 0


# --- Create request ---
class DocumentCreateRequest(BaseModel):
    title: str = "Untitled document"


# --- batchUpdate ---
class Location(BaseModel):
    segmentId: str | None = None
    index: int


class Range(BaseModel):
    segmentId: str | None = None
    startIndex: int
    endIndex: int


class InsertTextRequest(BaseModel):
    location: Location
    text: str


class DeleteContentRangeRequest(BaseModel):
    range: Range


class SubstringMatchCriteria(BaseModel):
    text: str
    matchCase: bool = True


class ReplaceAllTextRequest(BaseModel):
    containsText: SubstringMatchCriteria
    replaceText: str


class BatchUpdateDocumentRequest(BaseModel):
    requests: list[dict] = []


class WriteControl(BaseModel):
    requiredRevisionId: str | None = None


class BatchUpdateDocumentResponse(BaseModel):
    documentId: str
    replies: list[dict] = []
    writeControl: WriteControl | None = None


# --- Comments ---
class ReplySchema(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    id: str
    author: dict | None = None
    content: str = ""
    createdTime: str | None = None
    modifiedTime: str | None = None


class CommentSchema(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    id: str
    documentId: str | None = None
    content: str = ""
    author: dict | None = None
    resolved: bool = False
    quotedText: str | None = None
    replies: list[ReplySchema] = []
    createdTime: str | None = None
    modifiedTime: str | None = None


class CommentCreateRequest(BaseModel):
    content: str
    quotedText: str | None = None


class CommentUpdateRequest(BaseModel):
    content: str | None = None
    quotedText: str | None = None


class ReplyCreateRequest(BaseModel):
    content: str


class CommentListResponse(BaseModel):
    comments: list[CommentSchema] = []
    count: int = 0


# --- Permissions ---
class PermissionSchema(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    id: str
    documentId: str | None = None
    type: str = "user"  # user, anyone
    role: str = "reader"  # owner, writer, commenter, reader
    emailAddress: str | None = None
    displayName: str | None = None
    createdTime: str | None = None


class PermissionCreateRequest(BaseModel):
    type: str = "user"
    role: str = "reader"
    emailAddress: str | None = None


class PermissionUpdateRequest(BaseModel):
    role: str


class PermissionListResponse(BaseModel):
    permissions: list[PermissionSchema] = []
    count: int = 0
