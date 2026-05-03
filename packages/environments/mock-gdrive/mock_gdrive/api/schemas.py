"""Pydantic response models matching Google Drive API v3 shapes."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserInfo(BaseModel):
    kind: str = "drive#user"
    displayName: str = ""
    emailAddress: str = ""
    me: bool = False
    photoLink: str | None = None
    permissionId: str | None = None


class ShortcutDetails(BaseModel):
    targetId: str
    targetMimeType: str
    targetResourceKey: str | None = None


class PermissionDetailItem(BaseModel):
    """Single entry in permissionDetails[]."""
    permissionType: str  # "file", "member"
    role: str
    inherited: bool = False
    inheritedFrom: str | None = None


class PermissionResource(BaseModel):
    kind: str = "drive#permission"
    id: str
    type: str  # user, group, domain, anyone
    role: str  # owner, organizer, fileOrganizer, writer, commenter, reader
    emailAddress: str | None = None
    displayName: str | None = None
    domain: str | None = None
    photoLink: str | None = None
    expirationTime: str | None = None
    pendingOwner: bool | None = None
    deleted: bool | None = None
    allowFileDiscovery: bool | None = None
    view: str | None = None
    permissionDetails: list[PermissionDetailItem] | None = None


class PermissionList(BaseModel):
    kind: str = "drive#permissionList"
    permissions: list[PermissionResource] = []
    nextPageToken: str | None = None


class ContentRestriction(BaseModel):
    readOnly: bool = False
    reason: str | None = None
    type: str | None = None


class LinkShareMetadata(BaseModel):
    securityUpdateEligible: bool = False
    securityUpdateEnabled: bool = False


class FileResource(BaseModel):
    kind: str = "drive#file"
    id: str
    name: str = ""
    mimeType: str = ""
    parents: list[str] | None = None
    starred: bool | None = None
    trashed: bool | None = None
    explicitlyTrashed: bool | None = None
    createdTime: str | None = None
    modifiedTime: str | None = None
    modifiedByMeTime: str | None = None
    viewedByMeTime: str | None = None
    sharedWithMeTime: str | None = None
    trashedTime: str | None = None
    size: str | None = None  # Drive API returns size as string (int64)
    description: str | None = None
    properties: dict | None = None
    appProperties: dict | None = None
    version: str | None = None  # Drive API returns version as string
    webViewLink: str | None = None
    webContentLink: str | None = None
    iconLink: str | None = None
    thumbnailLink: str | None = None
    hasThumbnail: bool | None = None
    writersCanShare: bool | None = None
    copyRequiresWriterPermission: bool | None = None
    shared: bool | None = None
    ownedByMe: bool | None = None
    viewedByMe: bool | None = None
    modifiedByMe: bool | None = None
    owners: list[UserInfo] | None = None
    lastModifyingUser: UserInfo | None = None
    sharingUser: UserInfo | None = None
    trashingUser: UserInfo | None = None
    shortcutDetails: ShortcutDetails | None = None
    capabilities: dict | None = None
    permissions: list[PermissionResource] | None = None
    permissionIds: list[str] | None = None
    hasAugmentedPermissions: bool | None = None
    spaces: list[str] | None = None
    folderColorRgb: str | None = None
    originalFilename: str | None = None
    fullFileExtension: str | None = None
    fileExtension: str | None = None
    md5Checksum: str | None = None
    sha1Checksum: str | None = None
    sha256Checksum: str | None = None
    headRevisionId: str | None = None
    quotaBytesUsed: str | None = None  # string (int64)
    isAppAuthorized: bool | None = None
    exportLinks: dict | None = None
    resourceKey: str | None = None
    linkShareMetadata: LinkShareMetadata | None = None
    contentRestrictions: list[ContentRestriction] | None = None
    imageMediaMetadata: dict | None = None
    videoMediaMetadata: dict | None = None
    driveId: str | None = None

    model_config = {"extra": "allow"}


class FileList(BaseModel):
    kind: str = "drive#fileList"
    files: list[FileResource] = []
    nextPageToken: str | None = None
    incompleteSearch: bool = False


class StorageQuota(BaseModel):
    limit: str | None = None  # string in real API
    usage: str = "0"
    usageInDrive: str = "0"
    usageInDriveTrash: str = "0"


class AboutResource(BaseModel):
    kind: str = "drive#about"
    user: UserInfo
    storageQuota: StorageQuota
    maxUploadSize: str = "5242880000"  # ~5GB
    canCreateDrives: bool = True
    canCreateTeamDrives: bool = True
    importFormats: dict = {}
    exportFormats: dict = {}
    maxImportSizes: dict = {}
    appInstalled: bool = False
    folderColorPalette: list[str] = []


class GeneratedIds(BaseModel):
    kind: str = "drive#generatedIds"
    ids: list[str] = []
    space: str = "drive"


class Channel(BaseModel):
    kind: str = "api#channel"
    id: str = ""
    resourceId: str = ""
    resourceUri: str = ""
    expiration: str | None = None


class StartPageToken(BaseModel):
    kind: str = "drive#startPageToken"
    startPageToken: str = "1"


# --- Comment / Reply schemas ---

class CommentResource(BaseModel):
    kind: str = "drive#comment"
    id: str
    author: UserInfo | None = None
    content: str = ""
    htmlContent: str | None = None
    createdTime: str | None = None
    modifiedTime: str | None = None
    resolved: bool = False
    deleted: bool = False
    anchor: str | None = None
    quotedFileContent: dict | None = None
    replies: list["ReplyResource"] = []


class CommentList(BaseModel):
    kind: str = "drive#commentList"
    comments: list[CommentResource] = []
    nextPageToken: str | None = None


class ReplyResource(BaseModel):
    kind: str = "drive#reply"
    id: str
    author: UserInfo | None = None
    content: str = ""
    htmlContent: str | None = None
    createdTime: str | None = None
    modifiedTime: str | None = None
    deleted: bool = False
    action: str | None = None


class ReplyList(BaseModel):
    kind: str = "drive#replyList"
    replies: list[ReplyResource] = []
    nextPageToken: str | None = None


# --- Revision schema ---

class RevisionResource(BaseModel):
    kind: str = "drive#revision"
    id: str
    mimeType: str | None = None
    modifiedTime: str | None = None
    lastModifyingUser: UserInfo | None = None
    size: str | None = None  # int64 as string
    md5Checksum: str | None = None
    originalFilename: str | None = None
    keepForever: bool = False
    published: bool = False
    publishAuto: bool = False
    publishedOutsideDomain: bool = False
    publishedLink: str | None = None
    exportLinks: dict | None = None


class RevisionList(BaseModel):
    kind: str = "drive#revisionList"
    revisions: list[RevisionResource] = []
    nextPageToken: str | None = None


# --- Change schema ---

# --- Drive (Shared Drive) schemas ---

class DriveResource(BaseModel):
    kind: str = "drive#drive"
    id: str
    name: str = ""
    createdTime: str | None = None
    hidden: bool = False
    colorRgb: str | None = None
    themeId: str | None = None
    orgUnitId: str | None = None
    backgroundImageLink: str | None = None
    backgroundImageFile: dict | None = None
    capabilities: dict | None = None
    restrictions: dict | None = None


class DriveList(BaseModel):
    kind: str = "drive#driveList"
    drives: list[dict] = []
    nextPageToken: str | None = None


class ChangeResource(BaseModel):
    kind: str = "drive#change"
    changeType: str = "file"
    time: str | None = None
    fileId: str | None = None
    file: FileResource | None = None
    removed: bool = False
    driveId: str | None = None
    drive: dict | None = None


class ChangeList(BaseModel):
    kind: str = "drive#changeList"
    changes: list[ChangeResource] = []
    nextPageToken: str | None = None
    newStartPageToken: str | None = None
