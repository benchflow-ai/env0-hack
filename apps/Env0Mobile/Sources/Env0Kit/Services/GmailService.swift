import Foundation

/// Typed access to the env-0 Gmail mock (`/gmail/v1`).
///
/// One instance wraps a single mailbox; `userId` defaults to `"me"` everywhere,
/// matching the mock's identity resolution. All paths and JSON shapes mirror the
/// Gmail REST API.
public struct GmailService: Sendable {
    private let client: any Env0Requesting

    public init(client: any Env0Requesting) {
        self.client = client
    }

    private static let basePath = "/gmail/v1"

    // MARK: - Threads

    /// List thread stubs, optionally filtered by a Gmail `q` search string and
    /// label ids. Returns `[]` rather than nil when the server omits `threads`.
    public func listThreads(
        userId: String = "me",
        query: String? = nil,
        labelIds: [String] = [],
        maxResults: Int? = nil,
        pageToken: String? = nil,
        includeSpamTrash: Bool? = nil
    ) async throws -> GmailThreadList {
        var items: [URLQueryItem] = []
        if let item = URLQueryItem.optional("q", query) { items.append(item) }
        for labelId in labelIds {
            items.append(URLQueryItem(name: "labelIds", value: labelId))
        }
        if let maxResults {
            items.append(URLQueryItem(name: "maxResults", value: String(maxResults)))
        }
        if let item = URLQueryItem.optional("pageToken", pageToken) { items.append(item) }
        if let includeSpamTrash {
            items.append(URLQueryItem(name: "includeSpamTrash", value: includeSpamTrash ? "true" : "false"))
        }
        let endpoint = Endpoint(
            "\(Self.basePath)/users/\(userId)/threads",
            method: .get,
            query: items
        )
        return try await client.get(GmailThreadList.self, endpoint)
    }

    /// Fetch a thread and its messages (`format` defaults to `full`).
    public func getThread(
        id threadId: String,
        userId: String = "me",
        format: String? = nil
    ) async throws -> GmailThreadDetail {
        var items: [URLQueryItem] = []
        if let item = URLQueryItem.optional("format", format) { items.append(item) }
        let endpoint = Endpoint(
            "\(Self.basePath)/users/\(userId)/threads/\(threadId)",
            method: .get,
            query: items
        )
        return try await client.get(GmailThreadDetail.self, endpoint)
    }

    // MARK: - Labels

    /// List all labels for the mailbox. Returns `[]` when the server omits the
    /// `labels` key.
    public func listLabels(userId: String = "me") async throws -> [GmailLabel] {
        let endpoint = Endpoint(
            "\(Self.basePath)/users/\(userId)/labels",
            method: .get
        )
        let list = try await client.get(GmailLabelList.self, endpoint)
        return list.labels ?? []
    }

    // MARK: - Modify message labels

    /// Add and/or remove label ids on a message. Use `STARRED` to (un)star,
    /// `UNREAD` to mark unread/read, `TRASH` to trash/untrash. Returns the
    /// minimal message with its updated label set.
    @discardableResult
    public func modifyMessageLabels(
        messageId: String,
        addLabelIds: [String] = [],
        removeLabelIds: [String] = [],
        userId: String = "me"
    ) async throws -> GmailMinimalMessage {
        let body = GmailModifyLabelsRequest(
            addLabelIds: addLabelIds,
            removeLabelIds: removeLabelIds
        )
        let endpoint = Endpoint(
            "\(Self.basePath)/users/\(userId)/messages/\(messageId)/modify",
            method: .post,
            body: try JSONCoding.makeEncoder().encode(body)
        )
        return try await client.get(GmailMinimalMessage.self, endpoint)
    }

    /// Star a message (adds `STARRED`).
    @discardableResult
    public func star(messageId: String, userId: String = "me") async throws -> GmailMinimalMessage {
        try await modifyMessageLabels(messageId: messageId, addLabelIds: ["STARRED"], userId: userId)
    }

    /// Unstar a message (removes `STARRED`).
    @discardableResult
    public func unstar(messageId: String, userId: String = "me") async throws -> GmailMinimalMessage {
        try await modifyMessageLabels(messageId: messageId, removeLabelIds: ["STARRED"], userId: userId)
    }

    /// Mark a message read (removes `UNREAD`).
    @discardableResult
    public func markRead(messageId: String, userId: String = "me") async throws -> GmailMinimalMessage {
        try await modifyMessageLabels(messageId: messageId, removeLabelIds: ["UNREAD"], userId: userId)
    }

    /// Mark a message unread (adds `UNREAD`).
    @discardableResult
    public func markUnread(messageId: String, userId: String = "me") async throws -> GmailMinimalMessage {
        try await modifyMessageLabels(messageId: messageId, addLabelIds: ["UNREAD"], userId: userId)
    }

    /// Move a message to trash via the dedicated `/trash` endpoint.
    @discardableResult
    public func trash(messageId: String, userId: String = "me") async throws -> GmailMinimalMessage {
        let endpoint = Endpoint(
            "\(Self.basePath)/users/\(userId)/messages/\(messageId)/trash",
            method: .post
        )
        return try await client.get(GmailMinimalMessage.self, endpoint)
    }

    /// Remove a message from trash via the dedicated `/untrash` endpoint.
    @discardableResult
    public func untrash(messageId: String, userId: String = "me") async throws -> GmailMinimalMessage {
        let endpoint = Endpoint(
            "\(Self.basePath)/users/\(userId)/messages/\(messageId)/untrash",
            method: .post
        )
        return try await client.get(GmailMinimalMessage.self, endpoint)
    }

    // MARK: - Compose

    /// Send a composed message. `raw` is a base64url-encoded (no padding)
    /// RFC2822 message; set `threadId` to reply within an existing thread.
    @discardableResult
    public func sendMessage(
        raw: String,
        threadId: String? = nil,
        userId: String = "me"
    ) async throws -> GmailMinimalMessage {
        let body = GmailSendRequest(raw: raw, threadId: threadId)
        let endpoint = Endpoint(
            "\(Self.basePath)/users/\(userId)/messages/send",
            method: .post,
            body: try JSONCoding.makeEncoder().encode(body)
        )
        return try await client.get(GmailMinimalMessage.self, endpoint)
    }

    /// Create a draft from a base64url RFC2822 message (optionally attached to a
    /// thread). The returned draft's `message` is in minimal form.
    @discardableResult
    public func createDraft(
        raw: String,
        threadId: String? = nil,
        userId: String = "me"
    ) async throws -> GmailDraft {
        let body = GmailDraftCreateRequest(
            message: GmailSendRequest(raw: raw, threadId: threadId)
        )
        let endpoint = Endpoint(
            "\(Self.basePath)/users/\(userId)/drafts",
            method: .post,
            body: try JSONCoding.makeEncoder().encode(body)
        )
        return try await client.get(GmailDraft.self, endpoint)
    }
}
