import Foundation

/// A Gmail message. The full `MessageSchema`; absent fields are omitted by the
/// server (never null), so everything past the ids is optional. The same type
/// also decodes the minimal form (`{id, threadId, labelIds}`) returned by
/// modify/send/draft-create, since all full-only fields are optional.
public struct GmailMessage: Decodable, Sendable {
    public let id: String
    public let threadId: String?
    public let labelIds: [String]?
    public let snippet: String?
    public let historyId: String?
    /// Epoch milliseconds delivered as a string, e.g. `"1750257120000"`.
    public let internalDate: String?
    public let sizeEstimate: Int?
    public let payload: GmailMessagePart?
    /// Present only for `format=raw`: base64url of the full RFC2822 message.
    public let raw: String?

    /// Parsed form of ``internalDate`` (Gmail epoch-millisecond string).
    public var internalDateDate: Date? { DateParsing.epochMillis(internalDate) }
}

/// A node in the MIME payload tree. Recursive: multipart parts carry `parts`.
public struct GmailMessagePart: Decodable, Sendable {
    public let partId: String?
    public let mimeType: String?
    public let filename: String?
    public let headers: [GmailHeader]?
    public let body: GmailMessagePartBody?
    public let parts: [GmailMessagePart]?
}

/// A single RFC2822 header `{name, value}`.
public struct GmailHeader: Decodable, Sendable {
    public let name: String
    public let value: String
}

/// The body of a MIME part. `data` is base64url (no padding) of the UTF-8 body
/// text; it is omitted for `format=metadata` and for container/attachment parts.
public struct GmailMessagePartBody: Decodable, Sendable {
    public let attachmentId: String?
    public let size: Int?
    public let data: String?
}

/// The minimal message shape returned by modify / trash / send
/// (`{id, threadId, labelIds}`).
public struct GmailMinimalMessage: Decodable, Sendable {
    public let id: String
    public let threadId: String?
    public let labelIds: [String]?
}
