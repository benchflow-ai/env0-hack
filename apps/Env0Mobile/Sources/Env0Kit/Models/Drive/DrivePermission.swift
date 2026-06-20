import Foundation

/// The grantee category of a permission. Unknown server values fall back to
/// `.unknown` rather than throwing.
public enum DrivePermissionType: String, Decodable, Sendable {
    case user
    case group
    case domain
    case anyone
    case unknown

    public init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = DrivePermissionType(rawValue: raw) ?? .unknown
    }
}

/// The access level a permission grants. Unknown server values fall back to
/// `.unknown` rather than throwing.
public enum DrivePermissionRole: String, Decodable, Sendable {
    case owner
    case organizer
    case fileOrganizer
    case writer
    case commenter
    case reader
    case unknown

    public init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = DrivePermissionRole(rawValue: raw) ?? .unknown
    }
}

/// One entry in a permission's `permissionDetails` (inheritance breakdown).
public struct DrivePermissionDetail: Decodable, Sendable {
    /// `"file"` or `"member"`.
    public let permissionType: String?
    public let role: DrivePermissionRole?
    public let inherited: Bool?
    public let inheritedFrom: String?
}

/// A Drive permission resource (`drive#permission`). All optional past `kind`
/// because the server emits `exclude_none` and `fields` can project it down.
public struct DrivePermission: Decodable, Sendable {
    public let kind: String?
    /// 32-hex id (the owner permission too); NOT the user id.
    public let id: String?
    public let type: DrivePermissionType?
    public let role: DrivePermissionRole?
    /// Present for `user`/`group`; omitted for `anyone`.
    public let emailAddress: String?
    public let displayName: String?
    /// Present for `type = domain`.
    public let domain: String?
    public let photoLink: String?
    /// ISO8601 + `Z`.
    public let expirationTime: String?
    public let pendingOwner: Bool?
    public let deleted: Bool?
    /// Present for `anyone`/`domain`.
    public let allowFileDiscovery: Bool?
    public let view: String?
    public let permissionDetails: [DrivePermissionDetail]?

    /// Parsed expiration instant (RFC3339).
    public var expirationTimeDate: Date? { DateParsing.rfc3339(expirationTime) }
}

/// Envelope for `permissions.list` (`drive#permissionList`). `permissions` is
/// optional per the list-envelope convention; the service exposes `?? []`.
public struct DrivePermissionList: Decodable, Sendable {
    public let kind: String?
    public let nextPageToken: String?
    /// Optional per the list-envelope convention; the service exposes `?? []`.
    public let permissions: [DrivePermission]?
}
