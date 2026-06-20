import Foundation

/// Typed client for the env-0 mock Google Drive service (`/drive/v3`).
///
/// Mirrors the real Drive v3 wire format, so it points at a running env-0
/// instance (port 9005 / `DRIVE_URL`) instead of `www.googleapis.com`. Build it
/// with the drive-scoped ``Env0APIClient`` (its `baseURL` is the service root;
/// this type adds the `/drive/v3` path prefix).
///
/// Identity is header-driven on the mock (`X-Mock-Drive-User`) with a default
/// user fallback — there is no `me`/`primary`/`{userId}` path concept, so no
/// method here takes a `userId`. To act as a non-default user, configure the
/// header on the injected client.
public struct DriveService: Sendable {
    private let client: any Env0Requesting

    public init(client: any Env0Requesting) {
        self.client = client
    }

    private static let prefix = "/drive/v3"

    // MARK: - List

    /// List files (`files.list`).
    ///
    /// Projection note: without `fields`, each item is minimized to
    /// `kind,id,name,mimeType`. Pass a `files(...)` sub-spec (e.g.
    /// `"files(id,name,mimeType,modifiedTime,size,owners),nextPageToken"`) to get
    /// rich fields back. Trashed files are excluded unless the literal substring
    /// `trashed` appears in `q`.
    /// - Parameters:
    ///   - q: search query in Drive's `q` grammar (e.g. `name contains 'Budget'`).
    ///   - fields: field projection; omit for the minimal `kind,id,name,mimeType`.
    ///   - orderBy: comma list with optional ` desc` (default `modifiedTime desc`).
    ///   - pageSize: 1–1000 (default 100 server-side).
    ///   - pageToken: opaque token (a stringified offset) from a prior `nextPageToken`.
    /// - Returns: the file list; `files` is exposed as `[]` when the server omits it.
    public func listFiles(
        q: String? = nil,
        fields: String? = nil,
        orderBy: String? = nil,
        pageSize: Int? = nil,
        pageToken: String? = nil
    ) async throws -> DriveFileList {
        let query: [URLQueryItem] = [
            URLQueryItem.optional("q", q),
            URLQueryItem.optional("fields", fields),
            URLQueryItem.optional("orderBy", orderBy),
            URLQueryItem.optional("pageSize", pageSize.map(String.init)),
            URLQueryItem.optional("pageToken", pageToken),
        ].compactMap { $0 }
        let endpoint = Endpoint(
            "\(Self.prefix)/files",
            method: .get,
            query: query
        )
        return try await client.get(DriveFileList.self, endpoint)
    }

    // MARK: - Get metadata

    /// Fetch a file's metadata (`files.get`). With no `fields`, the full
    /// resource is returned (unlike list). Pass `fields=permissions(...)` to
    /// inline the permission array.
    /// - Parameters:
    ///   - fileId: a literal file id (no `"root"` alias).
    ///   - fields: optional projection over the full resource.
    public func getFile(
        fileId: String,
        fields: String? = nil
    ) async throws -> DriveFile {
        let query: [URLQueryItem] = [
            URLQueryItem.optional("fields", fields),
        ].compactMap { $0 }
        let endpoint = Endpoint(
            "\(Self.prefix)/files/\(fileId)",
            method: .get,
            query: query
        )
        return try await client.get(DriveFile.self, endpoint)
    }

    // MARK: - Content

    /// Download a non-Google file's raw bytes (`files.get` with `alt=media`).
    ///
    /// Returns the verbatim bytes (no base64). For Google-native types
    /// (`application/vnd.google-apps.*`) the server returns `403` — use
    /// ``exportFile(fileId:mimeType:)`` instead.
    public func downloadFileContent(fileId: String) async throws -> Data {
        let endpoint = Endpoint(
            "\(Self.prefix)/files/\(fileId)",
            method: .get,
            query: [URLQueryItem(name: "alt", value: "media")]
        )
        return try await client.run(endpoint)
    }

    /// Export a Google-native file's content (`files.export`).
    ///
    /// Returns the document's text content (UTF-8) as raw bytes. To read a Doc's
    /// body, request `mimeType: "text/plain"` and decode the `Data` as UTF-8.
    /// `400` if the source type isn't exportable or the requested `mimeType`
    /// isn't allowed for it.
    /// - Parameters:
    ///   - fileId: the Google-native file id.
    ///   - mimeType: target export format (required), e.g. `text/plain`.
    public func exportFile(fileId: String, mimeType: String) async throws -> Data {
        let endpoint = Endpoint(
            "\(Self.prefix)/files/\(fileId)/export",
            method: .get,
            query: [URLQueryItem(name: "mimeType", value: mimeType)]
        )
        return try await client.run(endpoint)
    }

    // MARK: - Create

    /// Create a file (`files.create`, `POST /drive/v3/files`).
    ///
    /// Sends the metadata as JSON. The new file is owned by the current request
    /// user and an `owner` permission is auto-created. Returns the full
    /// `FileResource` (filtered by `fields` if provided). Create a folder with
    /// `mimeType: "application/vnd.google-apps.folder"`, or a Google Doc with
    /// `mimeType: "application/vnd.google-apps.document"` (and optional
    /// `contentText`).
    /// - Parameters:
    ///   - metadata: the file metadata body.
    ///   - fields: optional projection over the returned resource.
    public func createFile(
        metadata: DriveCreateFileRequest,
        fields: String? = nil
    ) async throws -> DriveFile {
        let query: [URLQueryItem] = [
            URLQueryItem.optional("fields", fields),
        ].compactMap { $0 }
        let endpoint = Endpoint(
            "\(Self.prefix)/files",
            method: .post,
            query: query,
            body: try JSONCoding.makeEncoder().encode(metadata)
        )
        return try await client.get(DriveFile.self, endpoint)
    }

    // MARK: - Permissions

    /// List a file's permissions (`permissions.list`). Returns `[]` rather than
    /// nil when the server omits `permissions`.
    /// - Parameters:
    ///   - fileId: the file id.
    ///   - fields: optional projection, e.g. `permissions(id,type,role,emailAddress,displayName)`.
    ///   - pageSize: 1–100 (no real pagination; all perms are returned).
    ///   - pageToken: accepted for parity.
    public func getFilePermissions(
        fileId: String,
        fields: String? = nil,
        pageSize: Int? = nil,
        pageToken: String? = nil
    ) async throws -> [DrivePermission] {
        let query: [URLQueryItem] = [
            URLQueryItem.optional("fields", fields),
            URLQueryItem.optional("pageSize", pageSize.map(String.init)),
            URLQueryItem.optional("pageToken", pageToken),
        ].compactMap { $0 }
        let endpoint = Endpoint(
            "\(Self.prefix)/files/\(fileId)/permissions",
            method: .get,
            query: query
        )
        let list = try await client.get(DrivePermissionList.self, endpoint)
        return list.permissions ?? []
    }
}
