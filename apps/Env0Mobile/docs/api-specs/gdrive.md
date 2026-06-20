I have all the information needed. Let me verify the about endpoint shape briefly (for completeness of "me"/userId resolution context) and confirm there are no `exportLinks` populated, then write the spec.

I have enough. Here is the complete spec.

---

# Mock Google Drive API — iOS Client Spec (gdrive)

A FastAPI mock of Google Drive API **v3**. Wire format mirrors the real `https://www.googleapis.com/drive/v3` API, so an iOS client points at the local base URL instead. This spec covers: **list files**, **get file metadata**, **download/export content**, **create file**, and **get file permissions**.

## Connection

| | |
|---|---|
| Service | `gdrive` |
| Port | `9005` |
| Env var (URL) | `DRIVE_URL` (e.g. `http://localhost:9005`) |
| DB path | `/data/gdrive.db` |
| API version prefix | `/drive/v3` (upload alias: `/upload/drive/v3`) |

All Drive endpoints below are relative to the base URL, e.g. `GET {DRIVE_URL}/drive/v3/files`.

## Authentication

**By default the mock ignores auth entirely.** No `Authorization` header or token is required for any Drive endpoint. The current user is resolved per request (`resolve_user` in `api/deps.py`) in this order:

1. Header `X-Mock-Drive-User: <userId-or-email>` — explicit identity (e.g. `user_alex` or `alex@nexusai.com`).
2. Header `Authorization: Bearer <userId-or-email>` — the bearer value is treated as a **user id or email**, NOT a real JWT. (If the value matches no user → `401`.)
3. Fallback: the **first user in the DB** (the seed primary user, `user_alex` / `alex@nexusai.com`).

So with no headers at all, you act as the default seeded user (Alex Chen). To act as someone else, send `X-Mock-Drive-User`.

**Optional hardened mode** (only when the server is started with env `AUTH_ENABLED=1`, off by default): a real OIDC JWT is then required in `Authorization: Bearer <jwt>`; the token's `sub`/`email` maps to a local user. In that mode, `GET /drive/v3/files/{fileId}?alt=media` additionally requires a content-download scope (`drive.readonly` or `drive.full`), else `403`. Web UI routes (`/`, `/file/...`, `/switch-user`) and `/mcp`, `/health`, `/_admin/*` stay exempt. **For a normal mobile client against the default server, treat auth as absent.**

### Error envelope

Non-2xx Drive errors use this shape (HTTP status mirrored in `code`):

```json
{
  "error": {
    "code": 404,
    "message": "File not found: abc123",
    "status": "NOT_FOUND",
    "errors": [
      { "message": "File not found: abc123", "domain": "global", "reason": "notFound" }
    ]
  }
}
```

`status`/`reason` pairs: 400 `INVALID_ARGUMENT`/`badRequest`, 401 `UNAUTHENTICATED`/`unauthorized`, 403 `PERMISSION_DENIED`/`forbidden`, 404 `NOT_FOUND`/`notFound`, 409 `ALREADY_EXISTS`/`conflict`, 429 `RESOURCE_EXHAUSTED`/`rateLimitExceeded`, 500 `INTERNAL`/`backendError`. Pydantic body-validation failures are remapped to `400` with `reason: "required"`.

## Health & admin (brief)

**`GET /health`** → `{"status": "ok"}` (readiness gate; no auth).

**`GET /_admin/state`** → full world dump (verifier-facing, not for the client UI):
```json
{
  "users": { "user_alex": { "user": { "id": "user_alex", "email": "alex@nexusai.com", "displayName": "Alex Chen", "storageQuotaLimit": 15000000000, "storageUsed": 0 } } },
  "files": [ { "id": "...", "name": "...", "mimeType": "...", "parentId": "...|null", "ownerId": "user_alex", "lastModifyingUserId": "user_alex", "createdTime": "ISO8601", "modifiedTime": "ISO8601", "viewedByMeTime": "ISO8601|null", "trashed": false, "starred": false, "explicitlyTrashed": false, "size": 1234, "description": null, "properties": null, "version": 1, "webViewLink": null, "writersCanShare": true, "shortcutTargetId": null, "shortcutTargetMimeType": null, "hasContentText": true, "hasContentBlob": false } ],
  "permissions": [ { "id": "...", "fileId": "...", "role": "owner", "type": "user", "emailAddress": "alex@nexusai.com", "displayName": "Alex Chen", "domain": null, "inherited": false, "inheritedFrom": null, "expirationTime": null, "pendingOwner": false } ],
  "timestamp": "ISO8601"
}
```
Note `_admin/state` uses **different/snake-ish field names** (`parentId`, `ownerId`, `emailAddress`) than the public Drive API resources below — do not model your client on it.

## ID & value conventions (apply throughout)

- **File ids**: 32-char lowercase hex (`uuid4().hex`), e.g. `"7b3c9e1f4a2d4c8e9f0a1b2c3d4e5f60"`. Seeded files may have stable ids from task `needles.py`.
- **Permission ids**: 32-char hex (`uuid4().hex`). The owner permission's `id` is random hex (NOT the user id).
- **User ids**: human-readable seed strings: `user_alex`, `user_jordan`, `user_priya`, `user_marcus`, `user_sarah`, `user_investor`, `user_vendor`, `user_external`.
- **Emails (seed)**: `alex@nexusai.com` (Alex Chen, primary/default), `jordan@nexusai.com`, `priya@nexusai.com`, `marcus@nexusai.com`, `sarah@nexusai.com`, `david@sequoia.com` (David Park), `support@dataflow.io` (DataFlow Support), `external@example.com` (External Contractor, task scenarios only).
- **Timestamps**: RFC3339 with **millisecond** precision and `Z` suffix in Drive resources, e.g. `"2026-03-14T09:21:07.123Z"`. (Permission `expirationTime` uses `...isoformat() + "Z"`, microsecond precision.)
- **`size`, `version`, `quotaBytesUsed`** are returned as **strings** (int64-as-string). Google-native types (`application/vnd.google-apps.*`) return `size`/`md5Checksum`/`sha256Checksum` = `null`.
- **`parents`** is an array but holds at most one id (single-parent model); `[]` if at root.
- There is **no `{userId}` path param** anywhere (unlike Gmail). No `"me"`/`"primary"` literal resolution — identity comes from headers only. `fileId` is always a literal file id (no `"root"` alias support).

---

## 1. List files

`GET /drive/v3/files`

### Query params
| Param | Type | Default | Notes |
|---|---|---|---|
| `q` | string | — | Search query (see grammar below). |
| `pageSize` | int (1–1000) | `100` | |
| `pageToken` | string | — | Opaque, but is literally a numeric **offset** as a string (e.g. `"100"`). |
| `orderBy` | string | `modifiedTime desc` | Comma list; append ` desc` per field. Supported keys: `name`, `name_natural`, `modifiedTime`, `modifiedByMeTime`, `createdTime`, `folder`, `quotaBytesUsed`, `recency`, `sharedWithMeTime`, `starred`, `viewedByMeTime`. |
| `fields` | string | — | Field projection. **Critical** — see behavior below. |
| `corpora` | string | `user` | `user`/`allDrives` scope to files owned-by or shared-with the current user. |
| `spaces` | string | `drive` | |
| `includeItemsFromAllDrives`, `supportsAllDrives` | bool | `false` | Accepted, largely no-op. |

### `q` grammar (subset actually implemented)
Operators: `and`, `or`, `not`, parentheses. Comparisons: `=`, `!=`, `<`, `>`, `<=`, `>=`, `contains`, `<value> in parents`, `properties has { key='v' }`. String values are **single-quoted**. Supported fields: `name` (`=`, `contains`), `fullText contains 'x'` (matches name/content/description), `mimeType =`, `trashed =`, `starred =`, `modifiedTime`/`createdTime`/`viewedByMeTime` (compare to `'2026-01-01T00:00:00Z'`), `ownedByMe = true/false`, `sharedWithMe = true`, `description`, `writersCanShare`. Examples:
- `name contains 'Budget'`
- `mimeType = 'application/vnd.google-apps.document' and trashed = false`
- `'<folderId>' in parents`
- `modifiedTime > '2026-01-01T00:00:00Z'`

Trashed files are **excluded by default** unless the literal substring `trashed` appears in `q`. Invalid `q` → `400`.

### Response — the `fields` projection rule (non-obvious, important)
- **No `fields` param** → each file item is **minimized to only**: `kind`, `id`, `name`, `mimeType`. (Top-level `kind` is `"drive#fileList"`, plus `incompleteSearch`, optional `nextPageToken`.)
- **With `fields`** (e.g. `fields=files(id,name,mimeType,modifiedTime,size,owners),nextPageToken`) → each file is filtered to the requested sub-fields from the **full** resource (shape in §2). Always request a `files(...)` sub-spec to get rich fields.
- `nextPageToken` present only when more pages exist (`offset + pageSize < total`).

**Example (no `fields`):**
```json
{
  "kind": "drive#fileList",
  "incompleteSearch": false,
  "files": [
    { "kind": "drive#file", "id": "7b3c9e1f4a2d4c8e9f0a1b2c3d4e5f60", "name": "API Design Guide v3", "mimeType": "application/vnd.google-apps.document" },
    { "kind": "drive#file", "id": "a1b2c3d4e5f60718293a4b5c6d7e8f90", "name": "Q1 Budget.xlsx", "mimeType": "application/vnd.google-apps.spreadsheet" }
  ],
  "nextPageToken": "100"
}
```

**Example (`fields=files(id,name,mimeType,modifiedTime,size,owners(displayName,emailAddress)),nextPageToken`):**
```json
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
```
(Google-native docs have no `size`, so it's absent when filtered.)

Swift: model `FileList { kind: String; files: [DriveFile]; nextPageToken: String?; incompleteSearch: Bool? }`. Make every `DriveFile` field optional — projection means most can be missing.

---

## 2. Get file metadata

`GET /drive/v3/files/{fileId}`

### Query params
| Param | Type | Notes |
|---|---|---|
| `fields` | string | Projection over the full resource (§ below). If omitted, the **full** resource is returned (unlike list). |
| `alt` | string | `media` triggers content download — see §3. Omit for metadata. |
| `acknowledgeAbuse`, `supportsAllDrives`, `includePermissionsForView`, `includeLabels` | — | Accepted; minor/no-op. |

Errors: `404` if file id unknown; `403` if current user has no view access.

### Full `FileResource` JSON shape
All fields below are emitted with `exclude_none=True` (null fields are **omitted**, not sent as `null`). Make every field optional in Swift.

```json
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
  "thumbnailLink": "https://lh3.googleusercontent.com/drive-storage/placeholder_7b3c9e1f4a2d4c8e9f0a1b2c3d4e5f60",
  "hasThumbnail": false,
  "writersCanShare": true,
  "copyRequiresWriterPermission": false,
  "shared": true,
  "ownedByMe": true,
  "viewedByMe": false,
  "modifiedByMe": true,
  "owners": [
    { "kind": "drive#user", "displayName": "Alex Chen", "emailAddress": "alex@nexusai.com", "me": true, "permissionId": "user_alex" }
  ],
  "lastModifyingUser": {
    "kind": "drive#user", "displayName": "Alex Chen", "emailAddress": "alex@nexusai.com", "me": true, "permissionId": "user_alex"
  },
  "capabilities": {
    "canEdit": true, "canComment": true, "canShare": true, "canCopy": true, "canDownload": true,
    "canDelete": true, "canRename": true, "canTrash": true, "canUntrash": true, "canReadRevisions": true,
    "canAddChildren": false, "canListChildren": false, "canModifyContent": true, "canModifyLabels": true,
    "canReadLabels": true, "canChangeCopyRequiresWriterPermission": true, "canAcceptOwnership": false,
    "canMoveItemWithinDrive": true, "canMoveItemOutOfDrive": true
  },
  "spaces": ["drive"],
  "quotaBytesUsed": "5421",
  "isAppAuthorized": false,
  "hasAugmentedPermissions": true,
  "permissionIds": ["8f7e6d5c4b3a29180716253443526170", "1a2b3c4d5e6f70819293a4b5c6d7e8f9"],
  "headRevisionId": "rev_7b3c9e1f4a2d4c8e9f0a1b2c3d4e5f60_7",
  "linkShareMetadata": { "securityUpdateEligible": false, "securityUpdateEnabled": true }
}
```

Field types / notes:
- `kind` always `"drive#file"`.
- `parents`: `[String]` (omitted/empty when at root).
- `size`, `version`, `quotaBytesUsed`: **String** (int64-as-string). For Google-native types `size`/`md5Checksum`/`sha256Checksum` are absent.
- Booleans: `starred`, `trashed`, `explicitlyTrashed`, `hasThumbnail`, `writersCanShare`, `copyRequiresWriterPermission`, `shared`, `ownedByMe`, `viewedByMe`, `modifiedByMe`, `isAppAuthorized`, `hasAugmentedPermissions`.
- Timestamps `createdTime`/`modifiedTime`/`modifiedByMeTime`/`viewedByMeTime`/`sharedWithMeTime`/`trashedTime`: RFC3339 ms+`Z` strings. `modifiedByMeTime`/`viewedByMe`/`modifiedByMe` are only set when the file is owned by the current user; `sharedWithMeTime`/`trashedTime` are conditional.
- `owners`: array of **`User`** objects: `{ kind:"drive#user", displayName, emailAddress, me:Bool, permissionId, photoLink? }`. `permissionId` here equals the user id (e.g. `user_alex`). `me` reflects the **current request user**.
- `lastModifyingUser`, `sharingUser`, `trashingUser`: same `User` shape (omitted when absent).
- `capabilities`: a **dictionary of ~42 boolean flags** (full set is computed; representative ones shown). Model as `[String: Bool]`.
- `shortcutDetails` (only for shortcuts): `{ "targetId": String, "targetMimeType": String, "targetResourceKey": String? }`.
- `permissions`: NOT included by default; request via `fields=permissions(...)` to inline the array (same items as §5). `permissionIds` is a `[String]` of permission ids.
- `iconLink`: `https://drive-thirdparty.googleusercontent.com/16/type/{mimeType}`. `thumbnailLink`: `https://lh3.googleusercontent.com/drive-storage/placeholder_{fileId}`.
- `headRevisionId`: `rev_{fileId}_{version}`.
- `exportLinks`, `webViewLink`, `webContentLink`, `md5Checksum`, `fileExtension`, `fullFileExtension`, `originalFilename`, `folderColorRgb`, `resourceKey`, `properties`, `appProperties` may be present depending on the file. The resource model allows **extra fields** (`extra="allow"`).

---

## 3. Download / export content

Two distinct operations depending on whether the file is a Google-native type.

### 3a. Download binary content — `GET /drive/v3/files/{fileId}?alt=media`
- For **non-Google** files (e.g. `application/pdf`, `image/png`, `text/plain`). Returns the raw bytes.
- Response is **NOT JSON**: status `200`, `Content-Type: <file.mimeType>`, header `Content-Disposition: attachment; filename="<name>"`, body = raw bytes (`content_blob`, empty if none). **No base64** — bytes are returned verbatim. Read as `Data` in Swift.
- For **Google-native** types (`application/vnd.google-apps.*`) this returns `403` with message *"Use files.export to download Google Docs editors files."* → use 3b instead.
- `404` unknown file; `403` no view access. (With `AUTH_ENABLED=1`, also needs a content-download scope.)

### 3b. Export Google-native content — `GET /drive/v3/files/{fileId}/export`
| Param | Type | Required |
|---|---|---|
| `mimeType` | string | **Yes** — target export format. |

- Returns the document's text content (`content_text`, UTF-8 encoded) as raw bytes with `Content-Type: <mimeType>`. **Not JSON, not base64.**
- Allowed `mimeType` per source type:
  - `application/vnd.google-apps.document` → `text/plain`, `text/html`, `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
  - `application/vnd.google-apps.spreadsheet` → `text/csv`, `text/tab-separated-values`, `application/pdf`, `...spreadsheetml.sheet`
  - `application/vnd.google-apps.presentation` → `text/plain`, `application/pdf`, `...presentationml.presentation`
- `400` if the source type isn't exportable, or the requested `mimeType` isn't allowed for that source; `404`/`403` as usual. Note the body is always the same stored text regardless of the requested format (mock simplification).

iOS guidance: to read a Doc's body, call `…/export?mimeType=text/plain` and decode the returned `Data` as UTF-8 text.

---

## 4. Create file

`POST /drive/v3/files`  (alias: `POST /upload/drive/v3/files`)

### Query params
| Param | Type | Notes |
|---|---|---|
| `fields` | string | Projection over the returned resource. |
| `uploadType` | string | Accepted (`media`/`multipart`/`resumable`); behavior inferred from `Content-Type`. |

### Request body — three accepted forms
1. **Metadata-only (JSON)** — `Content-Type: application/json`, body is the metadata object. Most common for the client.
2. **Multipart** — `Content-Type: multipart/...` with a part named `metadata` (JSON) and a part named `file` (bytes).
3. **Raw bytes** — any non-JSON body is stored as `content_blob` with default metadata.

### Metadata JSON fields (all optional)
| Field | Type | Default |
|---|---|---|
| `name` | string | `"Untitled"` |
| `mimeType` | string | `"application/octet-stream"` |
| `parents` | `[String]` | none → root. Only `parents[0]` is used; it **must exist and be a folder** else `404`/`400`. |
| `id` | string | server generates 32-hex if absent |
| `description` | string | — |
| `properties` | object (string→string) | — |
| `appProperties` | object | — |
| `starred` | bool | `false` |
| `writersCanShare` | bool | `true` |
| `copyRequiresWriterPermission` | bool | `false` |
| `folderColorRgb` | string | — |
| `contentText` | string | mock convenience: stored as exportable text (use this to give a Google-Doc body). |
| `shortcutDetails` | `{ "targetId": String, "targetMimeType": String }` | only when `mimeType = application/vnd.google-apps.shortcut` |

Create a **folder** by setting `mimeType: "application/vnd.google-apps.folder"`. Create a **Google Doc** with `mimeType: "application/vnd.google-apps.document"` (and optional `contentText`).

### Behavior
- The new file is owned by the current request user; an `owner` permission (type `user`, the user's email) is auto-created.
- Response: **HTTP `200`** (not 201), body = the **full `FileResource`** (same shape as §2), filtered by `fields` if provided.

**Example request:**
```json
POST /drive/v3/files?fields=id,name,mimeType,parents,createdTime
Content-Type: application/json

{ "name": "Launch Notes", "mimeType": "application/vnd.google-apps.document",
  "parents": ["c0ffee00112233445566778899aabbcc"], "contentText": "Kickoff agenda..." }
```
**Example response (`200`):**
```json
{
  "kind": "drive#file",
  "id": "deadbeefcafef00d0011223344556677",
  "name": "Launch Notes",
  "mimeType": "application/vnd.google-apps.document",
  "parents": ["c0ffee00112233445566778899aabbcc"],
  "createdTime": "2026-06-20T15:04:05.000Z"
}
```
(With no `fields`, the full resource of §2 is returned.)

---

## 5. Get file permissions

### 5a. List permissions — `GET /drive/v3/files/{fileId}/permissions`
| Param | Type | Notes |
|---|---|---|
| `pageSize` | int (1–100) | default 100 |
| `pageToken` | string | (no real pagination here; all perms returned) |
| `fields` | string | e.g. `permissions(id,type,role,emailAddress,displayName)` |

`404` unknown file; `403` if the current user has no role on the file.

**Response:**
```json
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
```

### 5b. Get one permission — `GET /drive/v3/files/{fileId}/permissions/{permissionId}`
Same `PermissionResource` shape as one array element above (single object, not wrapped). `404` if the permission id isn't on that file.

### `PermissionResource` field types
| Field | Type | Notes |
|---|---|---|
| `kind` | string | `"drive#permission"` |
| `id` | string | 32-hex (owner perm too); not the user id |
| `type` | string | `user` \| `group` \| `domain` \| `anyone` |
| `role` | string | `owner` \| `organizer` \| `fileOrganizer` \| `writer` \| `commenter` \| `reader` |
| `emailAddress` | string? | present for `user`/`group` (omitted for `anyone`) |
| `displayName` | string? | |
| `domain` | string? | present for `type=domain` |
| `photoLink` | string? | |
| `expirationTime` | string? | ISO8601 + `Z` |
| `pendingOwner` | bool? | |
| `deleted` | bool? | |
| `allowFileDiscovery` | bool? | for `anyone`/`domain` |
| `view` | string? | e.g. `"published"` |
| `permissionDetails` | array? | `[{ permissionType: "file"\|"member", role: String, inherited: Bool, inheritedFrom: String? }]` |

Null fields are omitted (`exclude_none=True`). The owner permission always has `role: "owner"`. A file is `shared` when it has more than one permission. Inherited (folder-derived) permissions, when present, set `inherited: true` and `inheritedFrom: <folderId>` in `permissionDetails`.

---

### Cross-cutting notes for the client
- **Everything is `exclude_none`** — never assume a field is present; decode all resource fields as optional.
- **No base64 anywhere** — `alt=media` and `export` return raw bytes; metadata JSON never embeds content.
- **`fields` controls payload size**: list returns only `kind,id,name,mimeType` unless you pass `fields=files(...)`. `get`/`create` return the full resource unless `fields` narrows it.
- **Pagination** is offset-based: `nextPageToken` is a stringified integer offset you pass back as `pageToken`.
- **Identity** is header-driven (`X-Mock-Drive-User`) with a default user fallback; there is no `me`/`primary`/`{userId}` path concept.