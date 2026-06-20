import Foundation

/// A Google-Docs document as returned by `GET /v1/documents/{id}` and
/// `POST /v1/documents`.
///
/// The rich style maps (`documentStyle`, `namedStyles`, `lists`, …) are kept as
/// free-form ``JSONValue`` objects — they round-trip but are not load-bearing for
/// reading/writing text. The text itself lives in
/// `body.content[].paragraph.elements[].textRun.content`; use ``plainText`` to
/// flatten it. All maps are omitted by the server when empty, so everything past
/// the ids is optional.
public struct GDocDocument: Decodable, Sendable {
    public let documentId: String
    public let title: String
    public let body: DocBody?
    public let revisionId: String?
    /// e.g. `"DEFAULT_FOR_CURRENT_ACCESS"`.
    public let suggestionsViewMode: String?
    public let documentStyle: [String: JSONValue]?
    public let namedStyles: [String: JSONValue]?
    public let lists: [String: JSONValue]?
    public let inlineObjects: [String: JSONValue]?
    public let headers: [String: JSONValue]?
    public let footers: [String: JSONValue]?
    public let footnotes: [String: JSONValue]?
    public let namedRanges: [String: JSONValue]?
    public let positionedObjects: [String: JSONValue]?

    /// Flattened plain-text content of the document.
    ///
    /// Concatenates every `textRun.content` across all paragraphs in document
    /// order (including the trailing `"\n"` each paragraph carries). Tables and
    /// tables-of-contents are descended into recursively so their cell text is
    /// included too. Returns `""` for a document with no body or no text.
    public var plainText: String {
        guard let body else { return "" }
        return DocTextExtractor.text(from: body.content)
    }
}

/// The document body: an ordered list of structural elements (the spec calls
/// index 0→1 a `sectionBreak`, then paragraphs).
public struct DocBody: Decodable, Sendable {
    public let content: [StructuralElement]?
}

/// One top-level structural element. Exactly one of `paragraph`, `sectionBreak`,
/// `table`, `tableOfContents` is present.
public struct StructuralElement: Decodable, Sendable {
    public let startIndex: Int?
    public let endIndex: Int?
    public let paragraph: Paragraph?
    public let sectionBreak: SectionBreak?
    public let table: Table?
    public let tableOfContents: TableOfContents?
}

/// A section break. `sectionStyle` is free-form and not load-bearing for text.
public struct SectionBreak: Decodable, Sendable {
    public let sectionStyle: [String: JSONValue]?
}

/// A paragraph: a run of inline `elements` plus optional paragraph/bullet styling.
public struct Paragraph: Decodable, Sendable {
    public let elements: [ParagraphElement]?
    public let paragraphStyle: ParagraphStyle?
    public let bullet: Bullet?
    public let positionedObjectIds: [String]?
}

/// One inline element of a paragraph. For text, only `textRun` matters.
public struct ParagraphElement: Decodable, Sendable {
    public let startIndex: Int?
    public let endIndex: Int?
    public let textRun: TextRun?
    public let inlineObjectElement: InlineObjectElement?
    public let pageBreak: PageBreak?
    public let footnoteReference: FootnoteReference?
    public let equation: Equation?
    public let person: Person?
}

/// A run of text. `content` includes the paragraph's trailing `"\n"`.
public struct TextRun: Decodable, Sendable {
    public let content: String?
    public let textStyle: TextStyle?
}

/// Character-level styling. Every field is optional and omitted when unset.
public struct TextStyle: Decodable, Sendable {
    public let bold: Bool?
    public let italic: Bool?
    public let underline: Bool?
    public let strikethrough: Bool?
    public let smallCaps: Bool?
    public let baselineOffset: String?
    public let fontSize: Magnitude?
    public let foregroundColor: [String: JSONValue]?
    public let backgroundColor: [String: JSONValue]?
    public let weightedFontFamily: [String: JSONValue]?
    /// `{"url": "..."}` or `{"headingId": "..."}`.
    public let link: [String: JSONValue]?
}

/// A measured quantity, e.g. `{"magnitude": 11, "unit": "PT"}`.
public struct Magnitude: Decodable, Sendable {
    public let magnitude: Double?
    public let unit: String?
}

/// Paragraph-level styling (named style, alignment, spacing, …).
public struct ParagraphStyle: Decodable, Sendable {
    /// `"NORMAL_TEXT"`, `"HEADING_1"`…`"HEADING_6"`, `"TITLE"`, `"SUBTITLE"`.
    public let namedStyleType: String?
    /// `"START"`, `"CENTER"`, `"END"`, `"JUSTIFIED"`.
    public let alignment: String?
    public let direction: String?
    public let lineSpacing: Double?
}

/// Bullet metadata for a list paragraph.
public struct Bullet: Decodable, Sendable {
    public let listId: String?
    public let nestingLevel: Int?
    public let textStyle: TextStyle?
}

public struct InlineObjectElement: Decodable, Sendable {
    public let inlineObjectId: String?
    public let textStyle: TextStyle?
}

public struct PageBreak: Decodable, Sendable {
    public let textStyle: TextStyle?
}

public struct FootnoteReference: Decodable, Sendable {
    public let footnoteId: String?
    public let footnoteNumber: String?
    public let textStyle: TextStyle?
}

public struct Equation: Decodable, Sendable {
    public let suggestedInsertionIds: [String]?
    public let suggestedDeletionIds: [String]?
}

public struct Person: Decodable, Sendable {
    public let personId: String?
    public let personProperties: PersonProperties?
    public let textStyle: TextStyle?
}

public struct PersonProperties: Decodable, Sendable {
    public let email: String?
    public let name: String?
}

/// A table. Only present when a document contains one.
public struct Table: Decodable, Sendable {
    public let rows: Int?
    public let columns: Int?
    public let tableRows: [TableRow]?
    public let tableStyle: [String: JSONValue]?
}

public struct TableRow: Decodable, Sendable {
    public let startIndex: Int?
    public let endIndex: Int?
    public let tableCells: [TableCell]?
    public let tableRowStyle: [String: JSONValue]?
}

public struct TableCell: Decodable, Sendable {
    public let startIndex: Int?
    public let endIndex: Int?
    public let content: [StructuralElement]?
    public let tableCellStyle: [String: JSONValue]?
}

public struct TableOfContents: Decodable, Sendable {
    public let content: [StructuralElement]?
}
