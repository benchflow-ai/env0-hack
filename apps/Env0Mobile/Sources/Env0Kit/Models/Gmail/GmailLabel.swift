import Foundation

/// The kind of a Gmail label. Unknown server values fall back to `.unknown`
/// rather than throwing.
public enum GmailLabelType: String, Decodable, Sendable {
    case system
    case user
    case unknown

    public init(from decoder: any Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = GmailLabelType(rawValue: raw) ?? .unknown
    }
}

/// Optional label color, present only when a color is set.
public struct GmailLabelColor: Decodable, Sendable {
    public let backgroundColor: String?
    public let textColor: String?
}

/// A Gmail label. In `labels.list` the count and visibility fields are sparse
/// (omitted on many system labels), so all but `id`/`name`/`type` are optional.
public struct GmailLabel: Decodable, Sendable {
    public let id: String
    public let name: String
    public let type: GmailLabelType
    public let messageListVisibility: String?
    public let labelListVisibility: String?
    public let messagesTotal: Int?
    public let messagesUnread: Int?
    public let threadsTotal: Int?
    public let threadsUnread: Int?
    public let color: GmailLabelColor?
}

/// Envelope for `GET /gmail/v1/users/{userId}/labels`.
public struct GmailLabelList: Decodable, Sendable {
    public let labels: [GmailLabel]?
}
