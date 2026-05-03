# API_NOTES.md -- mock-gdrive

## 1. Ground Truth

- **API docs**: https://developers.google.com/drive/api/reference/rest/v3
- **Discovery document**: https://www.googleapis.com/discovery/v1/apis/drive/v3/rest
- **Test account**: Google Workspace test account (OAuth 2.0, scopes: `drive`, `drive.file`)
- **Auth script**: `scripts/auth.py` (OAuth 2.0 desktop flow, stores `scripts/token.json`)
- **Capture script**: `scripts/capture_fixtures.py` (calls real API, saves to `tests/fixtures/real_gdrive/`)
- **API spec**: `tests/fixtures/gdrive_api_spec.json` (57 endpoints, 41 implemented)
- **Coverage map**: `tests/fixtures/mock_coverage.json`

## 2. API Quirks

_Append-only log of surprising behaviors observed during fixture capture._

- **2026-03-14**: `files.list` with no `fields` param returns only `{kind, id, name, mimeType}` per file -- not the full resource. This is intentional per the API docs ("partial resources").
- **2026-03-14**: `files.get` with `fields=*` returns 50+ fields; without `fields` it returns sparse response similar to list items.
- **2026-03-14**: Mutation responses (create/update/copy) return only `{kind, id, name, mimeType}` unless `fields=*` is specified.
- **2026-03-14**: `permissions.list` wraps results in `{kind: "drive#permissionList", permissions: [...]}` even for a single permission.
- **2026-03-14**: Empty collection responses still include the `kind` field and an empty array (e.g., `{kind: "drive#fileList", files: []}`).
- **2026-03-14**: `about.get` requires `fields=*` or explicit field list -- returns 400 with no fields param.
- **2026-03-14**: `storageQuota` values and `size`/`version` on files are returned as strings (int64 JSON encoding).
- **2026-03-14**: Real API uses opaque base64 page tokens; our mock uses integer offsets.
- **2026-03-14**: `files.generateIds` returns `{kind: "drive#generatedIds", ids: [...], space: "drive"}`.

## 3. Intentionally Skipped (16 methods)

| Method | Reason |
|--------|--------|
| `teamdrives.create/delete/get/list/update` (5) | Deprecated -- use `drives.*` |
| `files.download` | New long-running download; `files.get?alt=media` suffices |
| `files.listLabels` | Requires separate Labels API |
| `files.modifyLabels` | Requires separate Labels API |
| `accessproposals.get/list/resolve` (3) | Enterprise request-access flow |
| `approvals.get/list` (2) | Google Workspace add-on |
| `apps.get/list` (2) | Third-party app listing; meaningless in mock |
| `operations.get` | Long-running operation polling; only for `files.download` |

## 4. Known Simplifications

Implemented endpoints where mock behavior intentionally diverges from the real API.

- **`files.export`**: Returns `content_text` as-is regardless of requested output MIME type. No actual format conversion (Docs→PDF, Sheets→CSV). Agents parsing specific export formats may get unexpected results.
- **`files.watch` / `changes.watch`**: Returns a stub `Channel` resource with a generated ID and 24-hour expiration. No actual push notifications sent. Agents that poll via `changes.list` are unaffected.
- **`fullText contains`**: Uses SQL `LIKE` (case-insensitive substring match) across name, content_text, and description. No tokenization, stemming, or relevance ranking. Exact substring queries work; stemming-dependent queries ("running" matching "ran") will not.
- **Shortcut validation**: `files.create` with shortcut MIME type accepts any `targetId` without validating the target exists. Real API validates target existence and caller access.
- **Recursive trash**: Trashing a folder sets `trashed=true` on descendants but does not set `trashedTime` or `trashingUser` on children. Real API sets `trashedTime` on the folder; children inherit trashed state with `explicitlyTrashed=false`.
- **`changes.list` scope**: Records changes globally. `restrictToMyDrive` and `driveId` parameters are accepted but not enforced. Real API scopes changes per user/drive.
- **Revision content download**: `GET /files/{fileId}/revisions/{revisionId}?alt=media` not supported. Agents fetching specific revision content will get 404/405.
- **Comment `htmlContent`**: Stored as provided. No auto-generation from `content` field. Real API auto-generates `htmlContent` with proper escaping and formatting.
- **Permission copy on `files.copy`**: Only creates owner permission on the copy. Real API copies all permissions from the source file.
- **ETag / conditional requests**: Not implemented. No `If-Match`/`If-None-Match` support.
- **Natural sort**: Mock uses SQLite default string ordering. Real API uses natural sort ("File 2" before "File 10").
- **Resumable upload**: Not implemented. `google-api-python-client` defaults to resumable for large files but falls back to simple upload on error.

## 5. Key Design Choices

- **`fields` parameter**: Drives response shape. Without it, list endpoints return `{kind, id, name, mimeType}` per item. With `fields=*`, full resource is returned. Implemented via `apply_field_mask()` in `api/fields.py`.
- **Lark-based query parser**: `api/query_parser.py` parses `q` parameter using a Lark grammar supporting `=`, `!=`, `contains`, `in`, `and`, `or`, `not`, `has { key = value }`, and parenthetical grouping. Compiles to SQLAlchemy filters.
- **Capability computation**: `api/capabilities.py` computes all 43 capability flags dynamically from file ownership, role, mime type, shared drive membership, and file state (trashed, etc.).
- **Pagination**: Uses integer offset page tokens (e.g., `"10"`, `"20"`). Real API uses opaque base64 tokens. Agents treating tokens as opaque strings are unaffected.
- **Action logging**: All non-admin API calls are recorded in an in-memory action log for evaluation. Middleware in `api/app.py` captures method, path, user, body, and response status.

## 6. Open Questions

- **Content APIs** (Docs, Sheets, Slides): Separate Google products, not part of Drive API. If content editing is needed, build as separate environments (`mock-gdocs`, `mock-gsheets`) that compose with mock-gdrive.
