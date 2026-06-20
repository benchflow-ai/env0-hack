import Foundation

/// A Gmail draft. The nested `message` is minimal on create
/// (`{id, threadId, labelIds}`) and full when fetched via `drafts.get`; both
/// decode into ``GmailMessage`` because its full-only fields are optional.
public struct GmailDraft: Decodable, Sendable {
    public let id: String
    public let message: GmailMessage?
}
