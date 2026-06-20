import Foundation

/// Body for `POST /v1/documents` (create). Only `title` is read by the server;
/// it defaults `title` to `"Untitled document"` when omitted, so this helper
/// always sends the caller's title.
public struct CreateDocRequest: Encodable, Sendable {
    public let title: String

    public init(title: String) {
        self.title = title
    }
}

/// Body for `POST /doc/{id}/save` (web-editor full-content overwrite).
///
/// `content` is plain text (or HTML when `format == "html"`). For `"text"`, a
/// double newline starts a new paragraph; a single newline stays within one.
public struct SaveRequest: Encodable, Sendable {
    public let content: String
    /// `"text"` (default) or `"html"`.
    public let format: String

    public init(content: String, format: String = "text") {
        self.content = content
        self.format = format
    }
}

/// Response from `POST /doc/{id}/save`. Note: this route uses snake_case
/// `modified_time` (not the Google camelCase wire format elsewhere).
public struct SaveResponse: Decodable, Sendable {
    public let status: String
    public let modifiedTime: String?

    /// Parsed form of ``modifiedTime`` (RFC3339, with fractional seconds).
    public var modifiedTimeDate: Date? { DateParsing.rfc3339(modifiedTime) }

    enum CodingKeys: String, CodingKey {
        case status
        case modifiedTime = "modified_time"
    }
}

/// Body for `POST /v1/documents/{id}:batchUpdate` (canonical structured edits).
///
/// Each entry in `requests` is a free-form object with exactly one key naming
/// the operation (`insertText`, `replaceAllText`, `deleteContentRange`, …). The
/// ``DocsBatchUpdate`` factory builds the common shapes; you can also pass raw
/// `[String: JSONValue]` objects via ``init(requests:)``.
public struct BatchUpdateRequest: Encodable, Sendable {
    public let requests: [JSONValue]
    public let writeControl: WriteControl?

    public init(requests: [JSONValue], writeControl: WriteControl? = nil) {
        self.requests = requests
        self.writeControl = writeControl
    }
}

/// Optimistic-concurrency control for batchUpdate. Currently not enforced by the
/// mock, but accepted and echoed back with the new revision id.
public struct WriteControl: Codable, Sendable {
    public let requiredRevisionId: String?

    public init(requiredRevisionId: String?) {
        self.requiredRevisionId = requiredRevisionId
    }
}

/// Response from `:batchUpdate`. `replies` is parallel to the request array
/// (one entry per request; an empty object when the op has no reply payload).
/// `writeControl.requiredRevisionId` is the *new* revision id after the update.
/// The body is **not** returned — call ``DocsService/getDocument(documentId:userId:)``
/// to re-read content.
public struct BatchUpdateResponse: Decodable, Sendable {
    public let documentId: String?
    public let replies: [JSONValue]?
    public let writeControl: WriteControl?
}

/// Builders for the most common `:batchUpdate` request objects so callers don't
/// have to hand-assemble ``JSONValue`` trees.
public enum DocsBatchUpdate {
    /// `{ "insertText": { "location": {"index": index}, "text": text } }`
    public static func insertText(at index: Int, text: String) -> JSONValue {
        .object([
            "insertText": .object([
                "location": .object(["index": .number(Double(index))]),
                "text": .string(text),
            ]),
        ])
    }

    /// `{ "deleteContentRange": { "range": {"startIndex": .., "endIndex": ..} } }`
    public static func deleteContentRange(startIndex: Int, endIndex: Int) -> JSONValue {
        .object([
            "deleteContentRange": .object([
                "range": .object([
                    "startIndex": .number(Double(startIndex)),
                    "endIndex": .number(Double(endIndex)),
                ]),
            ]),
        ])
    }

    /// `{ "replaceAllText": { "containsText": {"text": .., "matchCase": ..}, "replaceText": .. } }`
    public static func replaceAllText(
        containing text: String,
        matchCase: Bool = true,
        with replaceText: String
    ) -> JSONValue {
        .object([
            "replaceAllText": .object([
                "containsText": .object([
                    "text": .string(text),
                    "matchCase": .bool(matchCase),
                ]),
                "replaceText": .string(replaceText),
            ]),
        ])
    }
}

extension JSONValue: Encodable {
    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }
}
