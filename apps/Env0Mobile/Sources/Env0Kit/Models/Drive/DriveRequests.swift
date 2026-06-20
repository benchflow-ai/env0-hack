import Foundation

/// Shortcut target sent when creating a shortcut file
/// (`mimeType = application/vnd.google-apps.shortcut`).
public struct DriveShortcutDetailsRequest: Encodable, Sendable {
    public var targetId: String
    public var targetMimeType: String

    public init(targetId: String, targetMimeType: String) {
        self.targetId = targetId
        self.targetMimeType = targetMimeType
    }
}

/// Metadata body for `files.create` (`POST /drive/v3/files`).
///
/// All fields are optional; the encoder omits nil keys, so the server applies
/// its defaults (`name = "Untitled"`, `mimeType = "application/octet-stream"`,
/// root parent, etc.). Set `mimeType` to `application/vnd.google-apps.folder`
/// for a folder or `application/vnd.google-apps.document` for a Google Doc;
/// `contentText` is a mock convenience that stores exportable text for a Doc.
/// `parents` holds at most one id (the target folder), which must exist.
public struct DriveCreateFileRequest: Encodable, Sendable {
    public var name: String?
    public var mimeType: String?
    public var parents: [String]?
    public var id: String?
    public var description: String?
    public var properties: [String: String]?
    public var appProperties: [String: String]?
    public var starred: Bool?
    public var writersCanShare: Bool?
    public var copyRequiresWriterPermission: Bool?
    public var folderColorRgb: String?
    /// Mock convenience: stored as exportable text (gives a Google-Doc body).
    public var contentText: String?
    public var shortcutDetails: DriveShortcutDetailsRequest?

    public init(
        name: String? = nil,
        mimeType: String? = nil,
        parents: [String]? = nil,
        id: String? = nil,
        description: String? = nil,
        properties: [String: String]? = nil,
        appProperties: [String: String]? = nil,
        starred: Bool? = nil,
        writersCanShare: Bool? = nil,
        copyRequiresWriterPermission: Bool? = nil,
        folderColorRgb: String? = nil,
        contentText: String? = nil,
        shortcutDetails: DriveShortcutDetailsRequest? = nil
    ) {
        self.name = name
        self.mimeType = mimeType
        self.parents = parents
        self.id = id
        self.description = description
        self.properties = properties
        self.appProperties = appProperties
        self.starred = starred
        self.writersCanShare = writersCanShare
        self.copyRequiresWriterPermission = copyRequiresWriterPermission
        self.folderColorRgb = folderColorRgb
        self.contentText = contentText
        self.shortcutDetails = shortcutDetails
    }
}
