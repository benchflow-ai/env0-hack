import Foundation

/// Typed client for the env-0 mock Google Docs service (`/v1`).
///
/// Mirrors the Google Docs API v1 wire format, so it points at a running env-0
/// instance (port 9004 / `DOCS_URL`) instead of `docs.googleapis.com`. Build it
/// with the docs-scoped ``Env0APIClient`` (its `baseURL` is the service root;
/// this type adds the `/v1` path prefix).
///
/// Identity is resolved by the optional `X-Env-0-Gdoc-User` request header (a
/// user id like `user_0` or an email). There is no `me` alias and no `userId`
/// path param: omit `userId` to act as the seeded primary user, or pass an
/// id/email to act as someone else.
public struct DocsService: Sendable {
    private let client: any Env0Requesting

    public init(client: any Env0Requesting) {
        self.client = client
    }

    /// All document JSON routes live under `/v1`.
    private static let prefix = "/v1"
    /// The identity header the gdoc mock reads (id or email).
    private static let userHeader = "X-Env-0-Gdoc-User"

    private static func identityHeaders(_ userId: String?) -> [String: String] {
        guard let userId, !userId.isEmpty else { return [:] }
        return [userHeader: userId]
    }

    // MARK: - Get

    /// Fetch a document with its full body (`GET /v1/documents/{documentId}`).
    ///
    /// - Parameters:
    ///   - documentId: the 32-char hex document id (from a create response or
    ///     `/_admin/state`; never hardcode it).
    ///   - userId: optional acting identity (`X-Env-0-Gdoc-User`); omit to act as
    ///     the seeded primary user. Access failures surface as HTTP 404.
    /// - Returns: the full ``GDocDocument`` (use ``GDocDocument/plainText`` to
    ///   read its text).
    public func getDocument(
        documentId: String,
        userId: String? = nil
    ) async throws -> GDocDocument {
        let endpoint = Endpoint(
            "\(Self.prefix)/documents/\(documentId)",
            method: .get,
            headers: Self.identityHeaders(userId)
        )
        return try await client.get(GDocDocument.self, endpoint)
    }

    // MARK: - Create

    /// Create a new, empty document (`POST /v1/documents`).
    ///
    /// The server ignores everything but `title` and returns the full created
    /// document (empty body: a section break plus one `"\n"` paragraph). The new
    /// document is owned by the resolved `userId`.
    public func createDocument(
        title: String,
        userId: String? = nil
    ) async throws -> GDocDocument {
        let body = try JSONCoding.makeEncoder().encode(CreateDocRequest(title: title))
        let endpoint = Endpoint(
            "\(Self.prefix)/documents",
            method: .post,
            headers: Self.identityHeaders(userId),
            body: body
        )
        return try await client.get(GDocDocument.self, endpoint)
    }

    // MARK: - Update content

    /// Overwrite a document's entire text via the web-editor save route
    /// (`POST /doc/{documentId}/save`). This is the simplest full-content update:
    /// it requires no permission check and rewrites the whole body, bumping the
    /// revision.
    ///
    /// - Parameters:
    ///   - documentId: the target document id.
    ///   - content: the new content (plain text, or HTML when `format == "html"`).
    ///   - format: `"text"` (default) or `"html"`.
    ///   - userId: optional acting identity.
    /// - Returns: a ``SaveResponse`` carrying `status` and the new `modifiedTime`.
    /// - Note: this route lives at the service root, **not** under `/v1`.
    @discardableResult
    public func saveDocument(
        documentId: String,
        content: String,
        format: String = "text",
        userId: String? = nil
    ) async throws -> SaveResponse {
        let body = try JSONCoding.makeEncoder().encode(
            SaveRequest(content: content, format: format)
        )
        let endpoint = Endpoint(
            "/doc/\(documentId)/save",
            method: .post,
            headers: Self.identityHeaders(userId),
            body: body
        )
        return try await client.get(SaveResponse.self, endpoint)
    }

    /// Apply structured edits to a document (`POST /v1/documents/{id}:batchUpdate`).
    ///
    /// Build `requests` with ``DocsBatchUpdate`` helpers (or raw ``JSONValue``
    /// objects, each with exactly one operation key). The response does not
    /// include the updated body — re-read with ``getDocument(documentId:userId:)``.
    ///
    /// - Parameters:
    ///   - documentId: the target document id.
    ///   - requests: the ordered list of edit operations.
    ///   - writeControl: optional concurrency control (accepted, not enforced).
    ///   - userId: optional acting identity; caller must be owner or have the
    ///     `writer` role (reader/commenter → 403, no access → 404).
    /// - Note: the path carries a literal `:batchUpdate` colon suffix.
    @discardableResult
    public func batchUpdate(
        documentId: String,
        requests: [JSONValue],
        writeControl: WriteControl? = nil,
        userId: String? = nil
    ) async throws -> BatchUpdateResponse {
        let body = try JSONCoding.makeEncoder().encode(
            BatchUpdateRequest(requests: requests, writeControl: writeControl)
        )
        let endpoint = Endpoint(
            "\(Self.prefix)/documents/\(documentId):batchUpdate",
            method: .post,
            headers: Self.identityHeaders(userId),
            body: body
        )
        return try await client.get(BatchUpdateResponse.self, endpoint)
    }
}
