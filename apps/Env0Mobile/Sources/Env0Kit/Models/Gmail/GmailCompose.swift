import Foundation

/// A plain-text message the UI can compose without knowing the Gmail `raw`
/// wire format. `rawValue()` produces the base64url (unpadded) RFC2822 string
/// that `GmailService.sendMessage(raw:)` / `createDraft(raw:)` expect.
public struct GmailCompose: Sendable, Equatable {
    public var to: String
    public var subject: String
    public var body: String
    public var cc: String?
    public var from: String?

    public init(to: String, subject: String, body: String, cc: String? = nil, from: String? = nil) {
        self.to = to
        self.subject = subject
        self.body = body
        self.cc = cc
        self.from = from
    }

    /// Serialize to a base64url-encoded RFC2822 message (no `=` padding), the
    /// form the Gmail API takes for `messages.send` / `drafts.create`.
    public func rawValue() -> String {
        var lines = [
            "MIME-Version: 1.0",
            "Content-Type: text/plain; charset=\"UTF-8\"",
        ]
        if let from, !from.isEmpty { lines.append("From: \(from)") }
        lines.append("To: \(to)")
        if let cc, !cc.isEmpty { lines.append("Cc: \(cc)") }
        lines.append("Subject: \(subject)")
        lines.append("")
        lines.append(body)
        let rfc2822 = lines.joined(separator: "\r\n")
        return Data(rfc2822.utf8).base64URLEncodedStringNoPadding()
    }
}

public extension GmailService {
    /// Convenience over ``sendMessage(raw:threadId:userId:)`` that builds the
    /// raw message from a ``GmailCompose``.
    @discardableResult
    func send(_ compose: GmailCompose, threadId: String? = nil, userId: String = "me") async throws -> GmailMinimalMessage {
        try await sendMessage(raw: compose.rawValue(), threadId: threadId, userId: userId)
    }

    /// Convenience over ``createDraft(raw:threadId:userId:)``.
    @discardableResult
    func draft(_ compose: GmailCompose, threadId: String? = nil, userId: String = "me") async throws -> GmailDraft {
        try await createDraft(raw: compose.rawValue(), threadId: threadId, userId: userId)
    }
}

extension Data {
    /// base64url without `=` padding (URL- and Gmail-safe alphabet).
    func base64URLEncodedStringNoPadding() -> String {
        base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}
