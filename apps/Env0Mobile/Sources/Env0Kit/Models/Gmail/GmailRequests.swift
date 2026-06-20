import Foundation

/// Request body for `messages.modify` — both arrays default to empty and are
/// always sent so the server sees an explicit (possibly empty) instruction.
public struct GmailModifyLabelsRequest: Encodable, Sendable {
    public let addLabelIds: [String]
    public let removeLabelIds: [String]

    public init(addLabelIds: [String] = [], removeLabelIds: [String] = []) {
        self.addLabelIds = addLabelIds
        self.removeLabelIds = removeLabelIds
    }
}

/// Request body for `messages.send`: a base64url RFC2822 message and an optional
/// thread id to reply within.
public struct GmailSendRequest: Encodable, Sendable {
    public let raw: String
    public let threadId: String?

    public init(raw: String, threadId: String? = nil) {
        self.raw = raw
        self.threadId = threadId
    }
}

/// Request body for `drafts.create`: the message nested under `message`
/// (`{"message":{"raw":...}}`).
public struct GmailDraftCreateRequest: Encodable, Sendable {
    public let message: GmailSendRequest

    public init(message: GmailSendRequest) {
        self.message = message
    }
}
