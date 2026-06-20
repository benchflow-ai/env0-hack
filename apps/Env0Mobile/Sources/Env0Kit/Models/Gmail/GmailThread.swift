import Foundation

/// A thread stub as returned by `threads.list` (no messages, just a snippet).
public struct GmailThread: Decodable, Sendable {
    public let id: String
    public let snippet: String
    /// Wire type is a string form of an int (e.g. `"1"`), not an Int.
    public let historyId: String?
}

/// Envelope for `GET /gmail/v1/users/{userId}/threads`.
///
/// Per the spec, `threads` and `nextPageToken` are omitted when absent, so both
/// are optional. The service exposes `threads ?? []`.
public struct GmailThreadList: Decodable, Sendable {
    public let resultSizeEstimate: Int
    public let threads: [GmailThread]?
    public let nextPageToken: String?
}

/// Full thread as returned by `threads.get`. There is no top-level `snippet`
/// key on this response (only `id`, `historyId`, `messages`).
public struct GmailThreadDetail: Decodable, Sendable {
    public let id: String
    public let historyId: String?
    public let messages: [GmailMessage]?
}
