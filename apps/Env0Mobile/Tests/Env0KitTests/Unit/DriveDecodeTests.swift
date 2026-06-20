import Foundation
import Testing
@testable import Env0Kit

@Suite("Drive fileList decoding")
struct DriveFileListDecodeTests {
    // Minimized list (no `fields`): items only carry kind,id,name,mimeType.
    let minimalJSON = """
    {
      "kind": "drive#fileList",
      "incompleteSearch": false,
      "files": [
        { "kind": "drive#file", "id": "7b3c9e1f4a2d4c8e9f0a1b2c3d4e5f60", "name": "API Design Guide v3", "mimeType": "application/vnd.google-apps.document" },
        { "kind": "drive#file", "id": "a1b2c3d4e5f60718293a4b5c6d7e8f90", "name": "Q1 Budget.xlsx", "mimeType": "application/vnd.google-apps.spreadsheet" }
      ],
      "nextPageToken": "100"
    }
    """

    @Test("decodes minimized list envelope")
    func decodesMinimal() throws {
        let list = try JSONCoding.makeDecoder().decode(DriveFileList.self, from: Data(minimalJSON.utf8))
        #expect(list.kind == "drive#fileList")
        #expect(list.incompleteSearch == false)
        #expect(list.nextPageToken == "100")
        let files = try #require(list.files)
        #expect(files.count == 2)
        #expect(files[0].name == "API Design Guide v3")
        #expect(files[0].mimeType == "application/vnd.google-apps.document")
        // Projected away on a minimal item -> nil, never a decode failure.
        #expect(files[0].size == nil)
        #expect(files[0].owners == nil)
        #expect(files[0].modifiedTime == nil)
    }

    @Test("absent files key surfaces as nil (service exposes [])")
    func absentFiles() throws {
        let json = #"{"kind":"drive#fileList"}"#
        let list = try JSONCoding.makeDecoder().decode(DriveFileList.self, from: Data(json.utf8))
        #expect(list.files == nil)
        #expect(list.nextPageToken == nil)
    }

    // Projected list with rich fields (fields=files(...),nextPageToken).
    let projectedJSON = """
    {
      "kind": "drive#fileList",
      "files": [
        {
          "kind": "drive#file",
          "id": "7b3c9e1f4a2d4c8e9f0a1b2c3d4e5f60",
          "name": "API Design Guide v3",
          "mimeType": "application/vnd.google-apps.document",
          "modifiedTime": "2026-03-14T09:21:07.123Z",
          "owners": [ { "kind": "drive#user", "displayName": "Alex Chen", "emailAddress": "alex@nexusai.com" } ]
        }
      ]
    }
    """

    @Test("decodes projected list with owners and modifiedTime date")
    func decodesProjected() throws {
        let list = try JSONCoding.makeDecoder().decode(DriveFileList.self, from: Data(projectedJSON.utf8))
        let files = try #require(list.files)
        let file = try #require(files.first)
        #expect(file.modifiedTime == "2026-03-14T09:21:07.123Z")
        let owners = try #require(file.owners)
        #expect(owners.first?.emailAddress == "alex@nexusai.com")
        // modifiedTime is parsed via DateParsing.rfc3339 (fractional seconds).
        let date = try #require(file.modifiedTimeDate)
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC")!
        let comps = utc.dateComponents([.year, .month, .day, .hour, .minute], from: date)
        #expect(comps.year == 2026 && comps.month == 3 && comps.day == 14 && comps.hour == 9 && comps.minute == 21)
        // nextPageToken absent on the last page.
        #expect(list.nextPageToken == nil)
    }
}

@Suite("Drive file metadata decoding")
struct DriveFileMetadataDecodeTests {
    let fullJSON = """
    {
      "kind": "drive#file",
      "id": "7b3c9e1f4a2d4c8e9f0a1b2c3d4e5f60",
      "name": "API Design Guide v3",
      "mimeType": "application/vnd.google-apps.document",
      "parents": ["c0ffee00112233445566778899aabbcc"],
      "starred": false,
      "trashed": false,
      "explicitlyTrashed": false,
      "createdTime": "2026-01-10T12:00:00.000Z",
      "modifiedTime": "2026-03-14T09:21:07.123Z",
      "modifiedByMeTime": "2026-03-14T09:21:07.123Z",
      "viewedByMeTime": "2026-03-14T09:21:07.123Z",
      "size": "5421",
      "description": "Engineering API standards",
      "version": "7",
      "iconLink": "https://drive-thirdparty.googleusercontent.com/16/type/application/vnd.google-apps.document",
      "hasThumbnail": false,
      "writersCanShare": true,
      "shared": true,
      "ownedByMe": true,
      "owners": [
        { "kind": "drive#user", "displayName": "Alex Chen", "emailAddress": "alex@nexusai.com", "me": true, "permissionId": "user_alex" }
      ],
      "lastModifyingUser": {
        "kind": "drive#user", "displayName": "Alex Chen", "emailAddress": "alex@nexusai.com", "me": true, "permissionId": "user_alex"
      },
      "capabilities": {
        "canEdit": true, "canComment": true, "canShare": true, "canDownload": true, "canAddChildren": false
      },
      "spaces": ["drive"],
      "quotaBytesUsed": "5421",
      "isAppAuthorized": false,
      "hasAugmentedPermissions": true,
      "permissionIds": ["8f7e6d5c4b3a29180716253443526170", "1a2b3c4d5e6f70819293a4b5c6d7e8f9"],
      "headRevisionId": "rev_7b3c9e1f4a2d4c8e9f0a1b2c3d4e5f60_7",
      "linkShareMetadata": { "securityUpdateEligible": false, "securityUpdateEnabled": true }
    }
    """

    @Test("decodes full file resource with string-typed numerics")
    func decodesFull() throws {
        let file = try JSONCoding.makeDecoder().decode(DriveFile.self, from: Data(fullJSON.utf8))
        #expect(file.id == "7b3c9e1f4a2d4c8e9f0a1b2c3d4e5f60")
        #expect(file.mimeType == "application/vnd.google-apps.document")
        // int64-as-string fields stay String.
        #expect(file.size == "5421")
        #expect(file.version == "7")
        #expect(file.quotaBytesUsed == "5421")
        // single-parent model.
        #expect(file.parents == ["c0ffee00112233445566778899aabbcc"])
        #expect(file.headRevisionId == "rev_7b3c9e1f4a2d4c8e9f0a1b2c3d4e5f60_7")
    }

    @Test("capabilities decode as a [String: Bool] dictionary")
    func decodesCapabilities() throws {
        let file = try JSONCoding.makeDecoder().decode(DriveFile.self, from: Data(fullJSON.utf8))
        let caps = try #require(file.capabilities)
        #expect(caps["canEdit"] == true)
        #expect(caps["canAddChildren"] == false)
        #expect(caps["canDownload"] == true)
    }

    @Test("user reference and nested metadata decode")
    func decodesUser() throws {
        let file = try JSONCoding.makeDecoder().decode(DriveFile.self, from: Data(fullJSON.utf8))
        let owner = try #require(file.owners?.first)
        #expect(owner.emailAddress == "alex@nexusai.com")
        #expect(owner.me == true)
        #expect(owner.permissionId == "user_alex")
        #expect(file.lastModifyingUser?.displayName == "Alex Chen")
        #expect(file.linkShareMetadata?.securityUpdateEnabled == true)
        #expect(file.permissionIds?.count == 2)
    }

    @Test("timestamps parse via DateParsing and omitted fields are nil")
    func decodesDatesAndSparse() throws {
        let file = try JSONCoding.makeDecoder().decode(DriveFile.self, from: Data(fullJSON.utf8))
        #expect(file.createdTime == "2026-01-10T12:00:00.000Z")
        let created = try #require(file.createdTimeDate)
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC")!
        let comps = utc.dateComponents([.year, .month, .day, .hour], from: created)
        #expect(comps.year == 2026 && comps.month == 1 && comps.day == 10 && comps.hour == 12)
        // exclude_none omits these -> nil, not a decode failure.
        #expect(file.sharedWithMeTime == nil)
        #expect(file.trashedTime == nil)
        #expect(file.webViewLink == nil)
        #expect(file.shortcutDetails == nil)
    }

    // Google-native types omit size/checksums entirely.
    @Test("google-native file omits size and md5Checksum")
    func googleNativeNoSize() throws {
        let json = """
        { "kind": "drive#file", "id": "abc", "name": "Doc", "mimeType": "application/vnd.google-apps.document" }
        """
        let file = try JSONCoding.makeDecoder().decode(DriveFile.self, from: Data(json.utf8))
        #expect(file.size == nil)
        #expect(file.md5Checksum == nil)
        #expect(file.sha256Checksum == nil)
    }
}

@Suite("Drive permission decoding")
struct DrivePermissionDecodeTests {
    let listJSON = """
    {
      "kind": "drive#permissionList",
      "permissions": [
        {
          "kind": "drive#permission",
          "id": "8f7e6d5c4b3a29180716253443526170",
          "type": "user",
          "role": "owner",
          "emailAddress": "alex@nexusai.com",
          "displayName": "Alex Chen",
          "permissionDetails": [
            { "permissionType": "file", "role": "owner", "inherited": false }
          ]
        },
        {
          "kind": "drive#permission",
          "id": "1a2b3c4d5e6f70819293a4b5c6d7e8f9",
          "type": "user",
          "role": "reader",
          "emailAddress": "david@sequoia.com",
          "displayName": "David Park",
          "permissionDetails": [
            { "permissionType": "file", "role": "reader", "inherited": false }
          ]
        },
        {
          "kind": "drive#permission",
          "id": "c001122334455667788990011aabbccdd",
          "type": "anyone",
          "role": "reader",
          "allowFileDiscovery": false,
          "permissionDetails": [ { "permissionType": "file", "role": "reader", "inherited": false } ]
        }
      ]
    }
    """

    @Test("decodes permission list with types, roles, and nested details")
    func decodesList() throws {
        let list = try JSONCoding.makeDecoder().decode(DrivePermissionList.self, from: Data(listJSON.utf8))
        let perms = try #require(list.permissions)
        #expect(perms.count == 3)

        let owner = perms[0]
        #expect(owner.type == .user)
        #expect(owner.role == .owner)
        #expect(owner.emailAddress == "alex@nexusai.com")
        #expect(owner.permissionDetails?.first?.permissionType == "file")
        #expect(owner.permissionDetails?.first?.inherited == false)

        // anyone permission has no emailAddress (omitted) but carries allowFileDiscovery.
        let anyone = perms[2]
        #expect(anyone.type == .anyone)
        #expect(anyone.emailAddress == nil)
        #expect(anyone.allowFileDiscovery == false)
        #expect(anyone.permissionDetails?.first?.role == .reader)
    }

    @Test("single permission decodes (permissions.get)")
    func decodesSingle() throws {
        let json = """
        {
          "kind": "drive#permission",
          "id": "8f7e6d5c4b3a29180716253443526170",
          "type": "user",
          "role": "writer",
          "emailAddress": "jordan@nexusai.com",
          "expirationTime": "2026-12-31T23:59:59Z"
        }
        """
        let perm = try JSONCoding.makeDecoder().decode(DrivePermission.self, from: Data(json.utf8))
        #expect(perm.role == .writer)
        #expect(perm.expirationTime == "2026-12-31T23:59:59Z")
        #expect(perm.expirationTimeDate != nil)
        #expect(perm.deleted == nil)
    }

    @Test("unknown role and type fall back to .unknown rather than throwing")
    func enumFallback() throws {
        let json = """
        { "kind": "drive#permission", "id": "x", "type": "starship", "role": "captain" }
        """
        let perm = try JSONCoding.makeDecoder().decode(DrivePermission.self, from: Data(json.utf8))
        #expect(perm.type == .unknown)
        #expect(perm.role == .unknown)
    }
}

@Suite("Drive create request encoding")
struct DriveCreateRequestEncodeTests {
    @Test("encodes metadata and omits nil keys")
    func encodesBody() throws {
        let req = DriveCreateFileRequest(
            name: "Launch Notes",
            mimeType: "application/vnd.google-apps.document",
            parents: ["c0ffee00112233445566778899aabbcc"],
            contentText: "Kickoff agenda..."
        )
        let data = try JSONCoding.makeEncoder().encode(req)
        let json = String(decoding: data, as: UTF8.self)
        #expect(json.contains("\"name\":\"Launch Notes\""))
        #expect(json.contains("\"mimeType\":\"application/vnd.google-apps.document\""))
        #expect(json.contains("\"contentText\":\"Kickoff agenda...\""))
        // Slashes are not escaped (encoder uses .withoutEscapingSlashes).
        #expect(json.contains("application/vnd.google-apps.document"))
        // nil fields omitted.
        #expect(!json.contains("\"description\""))
        #expect(!json.contains("\"starred\""))
        // Round-trips back through a Decodable view of the same field.
        struct Echo: Decodable { let name: String?; let parents: [String]? }
        let echo = try JSONCoding.makeDecoder().decode(Echo.self, from: data)
        #expect(echo.name == "Launch Notes")
        #expect(echo.parents == ["c0ffee00112233445566778899aabbcc"])
    }
}

@Suite("Drive created file response decoding")
struct DriveCreateResponseDecodeTests {
    @Test("decodes projected create response (200)")
    func decodesCreated() throws {
        let json = """
        {
          "kind": "drive#file",
          "id": "deadbeefcafef00d0011223344556677",
          "name": "Launch Notes",
          "mimeType": "application/vnd.google-apps.document",
          "parents": ["c0ffee00112233445566778899aabbcc"],
          "createdTime": "2026-06-20T15:04:05.000Z"
        }
        """
        let file = try JSONCoding.makeDecoder().decode(DriveFile.self, from: Data(json.utf8))
        #expect(file.id == "deadbeefcafef00d0011223344556677")
        #expect(file.name == "Launch Notes")
        #expect(file.parents == ["c0ffee00112233445566778899aabbcc"])
        #expect(file.createdTimeDate != nil)
        // Projected away -> nil.
        #expect(file.owners == nil)
        #expect(file.size == nil)
    }
}
