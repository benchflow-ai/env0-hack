import Foundation

/// A Drive user reference (`drive#user`), used by `owners`, `lastModifyingUser`,
/// `sharingUser`, and `trashingUser`. All fields are optional — the server emits
/// `exclude_none`, so absent fields are simply missing.
public struct DriveUser: Decodable, Sendable {
    public let kind: String?
    public let displayName: String?
    public let emailAddress: String?
    public let me: Bool?
    /// Equals the user id here (e.g. `user_alex`), NOT a permission id.
    public let permissionId: String?
    public let photoLink: String?
}

/// Target details carried only by shortcut files
/// (`mimeType = application/vnd.google-apps.shortcut`).
public struct DriveShortcutDetails: Decodable, Sendable {
    public let targetId: String?
    public let targetMimeType: String?
    public let targetResourceKey: String?
}

/// Link-share security metadata (`linkShareMetadata`).
public struct DriveLinkShareMetadata: Decodable, Sendable {
    public let securityUpdateEligible: Bool?
    public let securityUpdateEnabled: Bool?
}

/// A Drive file resource (`drive#file`).
///
/// Two things make every field optional:
/// 1. The server emits `exclude_none=True`, so null/empty fields are omitted.
/// 2. `files.list` *projects* each item down to the requested `fields` (only
///    `kind,id,name,mimeType` when no `fields` is passed), so even `id` can be
///    absent from a projected item.
///
/// `size`, `version`, and `quotaBytesUsed` arrive as int64-as-string and are
/// kept as `String`. Timestamps keep their raw RFC3339 (ms + `Z`) wire strings
/// and expose parsed `Date` values via computed properties using ``DateParsing``.
public struct DriveFile: Decodable, Sendable {
    public let kind: String?
    public let id: String?
    public let name: String?
    public let mimeType: String?
    /// At most one parent id (single-parent model); omitted/empty at root.
    public let parents: [String]?

    public let starred: Bool?
    public let trashed: Bool?
    public let explicitlyTrashed: Bool?

    /// Int64-as-string, e.g. `"5421"`. Absent for Google-native types.
    public let size: String?
    /// Int64-as-string, e.g. `"7"`.
    public let version: String?
    /// Int64-as-string, e.g. `"5421"`.
    public let quotaBytesUsed: String?

    public let description: String?

    // Raw RFC3339 (ms + `Z`) wire strings.
    public let createdTime: String?
    public let modifiedTime: String?
    public let modifiedByMeTime: String?
    public let viewedByMeTime: String?
    public let sharedWithMeTime: String?
    public let trashedTime: String?

    public let iconLink: String?
    public let thumbnailLink: String?
    public let webViewLink: String?
    public let webContentLink: String?
    public let hasThumbnail: Bool?

    public let writersCanShare: Bool?
    public let copyRequiresWriterPermission: Bool?
    public let shared: Bool?
    public let ownedByMe: Bool?
    public let viewedByMe: Bool?
    public let modifiedByMe: Bool?
    public let isAppAuthorized: Bool?
    public let hasAugmentedPermissions: Bool?

    public let owners: [DriveUser]?
    public let lastModifyingUser: DriveUser?
    public let sharingUser: DriveUser?
    public let trashingUser: DriveUser?

    /// ~42 capability boolean flags, modeled as a dictionary.
    public let capabilities: [String: Bool]?
    public let spaces: [String]?
    /// Permission ids on the file. The full `permissions` array is only present
    /// when requested via `fields=permissions(...)`.
    public let permissionIds: [String]?
    public let permissions: [DrivePermission]?
    public let headRevisionId: String?
    public let shortcutDetails: DriveShortcutDetails?
    public let linkShareMetadata: DriveLinkShareMetadata?

    public let md5Checksum: String?
    public let sha256Checksum: String?
    public let fileExtension: String?
    public let fullFileExtension: String?
    public let originalFilename: String?
    public let folderColorRgb: String?
    public let resourceKey: String?
    public let properties: [String: String]?
    public let appProperties: [String: String]?

    /// Parsed creation instant (RFC3339).
    public var createdTimeDate: Date? { DateParsing.rfc3339(createdTime) }
    /// Parsed last-modified instant (RFC3339).
    public var modifiedTimeDate: Date? { DateParsing.rfc3339(modifiedTime) }
    /// Parsed "modified by me" instant (RFC3339).
    public var modifiedByMeTimeDate: Date? { DateParsing.rfc3339(modifiedByMeTime) }
    /// Parsed "viewed by me" instant (RFC3339).
    public var viewedByMeTimeDate: Date? { DateParsing.rfc3339(viewedByMeTime) }
    /// Parsed "shared with me" instant (RFC3339).
    public var sharedWithMeTimeDate: Date? { DateParsing.rfc3339(sharedWithMeTime) }
    /// Parsed trashed instant (RFC3339).
    public var trashedTimeDate: Date? { DateParsing.rfc3339(trashedTime) }
}

/// Envelope for `files.list` (`drive#fileList`). `files` is optional per the
/// list-envelope convention; the service exposes `?? []`.
public struct DriveFileList: Decodable, Sendable {
    public let kind: String?
    public let incompleteSearch: Bool?
    /// Stringified integer offset; present only when more pages exist.
    public let nextPageToken: String?
    /// Optional per the list-envelope convention; the service exposes `?? []`.
    public let files: [DriveFile]?
}
