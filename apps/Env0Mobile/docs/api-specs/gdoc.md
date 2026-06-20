I now have everything needed. The primary user is `user_0` / `alex@nexusai.com`. Document IDs are 32-hex (uuid4 hex truncated to 44 chars, but uuid4 hex is 32 chars). Note: there is NO JSON REST "list documents" endpoint — only the human web UI at `/`. I'll document that explicitly.

# gdoc — Mock Google Docs API (HTTP spec for an iOS client)

## Connection

| | |
|---|---|
| **Service** | `gdoc` (Mock Google Docs REST API, modeled on Google Docs API **v1**) |
| **Port** | `9004` |
| **Env var** | `DOCS_URL` (this holds the full base URL, e.g. `http://localhost:9004`) |
| **API path prefix** | `/v1` (all document routes live under `/v1/...`) |
| **Error format** | Google-style envelope (see below) |

The base URL plus the route gives the full endpoint, e.g. `GET {DOCS_URL}/v1/documents/{documentId}`.

### Auth

Auth is **off by default**. The middleware that enforces tokens (`GdocEnv_0AuthMiddleware`) is only attached when the server is started with the environment variable `AUTH_ENABLED` set to `1`/`true`/`yes`. In the normal benchmark/mobile setup it is **not** set, so:

- **No `Authorization` header is required.** Send requests with no auth at all.
- Identity is resolved from an optional request header **`X-Env-0-Gdoc-User`** whose value is a user **id** (e.g. `user_0`) or **email** (e.g. `alex@nexusai.com`). If the header is absent, the server falls back to the **first user in the database** (the seeded primary user `user_0` / `alex@nexusai.com`). There is no `me` alias and no `userId` path param — this header is the only identity channel.

If `AUTH_ENABLED=1` (not the default), then:
- Every `/v1/...` route requires a valid Bearer token: header `Authorization: Bearer <JWT>`.
- Scopes (OR-logic, any one grants access): document reads (`GET /v1/documents/{id}`) need `docs.readonly` or `docs.full`; document **mutations** (`POST /v1/documents`, `:batchUpdate`) need `docs.full`.
- The web UI (`/`, `/doc/...`), `/health`, `/_admin/*`, `/dev/*`, `/mcp` stay exempt even with auth on.
- If `X-Env-0-Gdoc-User` names anyone other than the token's subject/email, a `403` impersonation error is returned (different body shape — not relevant to the read/write ops below).

An iOS client targeting the default (auth-off) deployment can ignore all of this and simply set `X-Env-0-Gdoc-User` to act as a specific user, or omit it to be the primary user.

### Standard error envelope

Any non-2xx (404/403/400/etc.) returns:

```json
{
  "error": {
    "code": 404,
    "message": "Document 'abc' not found",
    "status": "NOT_FOUND",
    "errors": [
      { "message": "Document 'abc' not found", "domain": "global", "reason": "notFound" }
    ]
  }
}
```

`status`/`reason` map by code: 400→`INVALID_ARGUMENT`/`badRequest` (also `required` for body-validation errors), 401→`UNAUTHENTICATED`/`unauthorized`, 403→`PERMISSION_DENIED`/`forbidden`, 404→`NOT_FOUND`/`notFound`, 409→`ALREADY_EXISTS`/`conflict`. Validation failures that FastAPI would normally return as 422 are remapped to **400** with this same shape.

Swift Codable for errors:
```swift
struct APIError: Codable { let error: APIErrorBody }
struct APIErrorBody: Codable {
  let code: Int; let message: String; let status: String
  let errors: [APIErrorDetail]
}
struct APIErrorDetail: Codable { let message: String; let domain: String; let reason: String }
```

### Health / admin (brief)

- **`GET /health`** → `{"status": "ok"}` (readiness gate; no auth, not logged).
- **`GET /_admin/state`** → full multi-user dump. Shape:
  ```json
  {
    "users": {
      "user_0": {
        "user": { "id": "user_0", "email": "alex@nexusai.com", "displayName": "Alex Thompson" },
        "documents": [ { "id": "...", "title": "...", "body": { "content": [...] },
                        "documentStyle": {...}, "namedStyles": {...}, "lists": {...},
                        "inlineObjects": {...}, "headers": {...}, "footers": {...},
                        "footnotes": {...}, "namedRanges": {...}, "positionedObjects": {...},
                        "revisionId": "...", "suggestionsViewMode": "DEFAULT_FOR_CURRENT_ACCESS",
                        "createdTime": "2026-...Z", "modifiedTime": "2026-...Z" } ],
        "comments": [ ... ], "permissions": [ ... ], "revisions": [ ... ]
      }
    },
    "timestamp": "2026-06-20T...Z"
  }
  ```
  This is the *only* way to enumerate documents over JSON (there is no public list endpoint — see "List documents" below). Keys of `users` are user ids; each user's `documents` is an array of the docs they **own**.

---

## Common types (shared by all document responses)

The document **body** is the rich Google-Docs structure. These types appear verbatim in get/create/batchUpdate responses. Key facts:

- Indices are **1-based**; the body always begins with a `sectionBreak` occupying index 0→1, then paragraphs. Every paragraph's text ends with a `"\n"`.
- All maps (`documentStyle`, `lists`, `inlineObjects`, `headers`, …) are **omitted from the response when empty** (`exclude_none` / non-empty-only). A brand-new doc still returns `documentStyle` and `namedStyles` (they are seeded non-empty) but typically omits `lists`, `inlineObjects`, `headers`, `footers`, `footnotes`, `namedRanges`, `positionedObjects`.
- There is **no base64 anywhere** — text is plain UTF-8 in `textRun.content`.

```swift
struct DocBody: Codable { let content: [StructuralElement] }

struct StructuralElement: Codable {
  let startIndex: Int?
  let endIndex: Int?
  let paragraph: Paragraph?
  let sectionBreak: SectionBreak?
  let table: Table?
  let tableOfContents: TableOfContents?
}

struct SectionBreak: Codable { let sectionStyle: [String: AnyCodable]? }

struct Paragraph: Codable {
  let elements: [ParagraphElement]
  let paragraphStyle: ParagraphStyle?
  let bullet: Bullet?
  let positionedObjectIds: [String]?
}

struct ParagraphElement: Codable {
  let startIndex: Int?
  let endIndex: Int?
  let textRun: TextRun?
  let inlineObjectElement: InlineObjectElement?
  let pageBreak: PageBreak?
  let footnoteReference: FootnoteReference?
  let equation: Equation?
  let person: Person?
}

struct TextRun: Codable {
  let content: String        // includes trailing "\n" for the paragraph
  let textStyle: TextStyle?
}

struct TextStyle: Codable {  // all optional; omitted when unset
  let bold: Bool?; let italic: Bool?; let underline: Bool?; let strikethrough: Bool?
  let smallCaps: Bool?; let baselineOffset: String?
  let fontSize: Magnitude?               // {"magnitude": 11, "unit": "PT"}
  let foregroundColor: [String: AnyCodable]?
  let backgroundColor: [String: AnyCodable]?
  let weightedFontFamily: [String: AnyCodable]?  // {"fontFamily":"Arial","weight":400}
  let link: [String: AnyCodable]?        // {"url": "..."} or {"headingId": "..."}
}

struct Magnitude: Codable { let magnitude: Double?; let unit: String? }  // unit e.g. "PT"

struct ParagraphStyle: Codable {
  let namedStyleType: String?  // "NORMAL_TEXT","HEADING_1"..."HEADING_6","TITLE","SUBTITLE"
  let alignment: String?       // "START","CENTER","END","JUSTIFIED"
  let direction: String?       // "LEFT_TO_RIGHT"
  let lineSpacing: Double?
  // many more optional fields: spaceAbove/spaceBelow (Magnitude), indent*, border*, etc.
}

struct Bullet: Codable { let listId: String; let nestingLevel: Int; let textStyle: TextStyle? }

struct InlineObjectElement: Codable { let inlineObjectId: String; let textStyle: TextStyle? }
struct PageBreak: Codable { let textStyle: TextStyle? }
struct FootnoteReference: Codable { let footnoteId: String; let footnoteNumber: String?; let textStyle: TextStyle? }
struct Equation: Codable { let suggestedInsertionIds: [String]?; let suggestedDeletionIds: [String]? }
struct Person: Codable { let personId: String?; let personProperties: PersonProperties?; let textStyle: TextStyle? }
struct PersonProperties: Codable { let email: String?; let name: String? }

// Tables (present only when a doc contains a table)
struct Table: Codable {
  let rows: Int; let columns: Int
  let tableRows: [TableRow]; let tableStyle: [String: AnyCodable]?
}
struct TableRow: Codable {
  let startIndex: Int?; let endIndex: Int?
  let tableCells: [TableCell]; let tableRowStyle: [String: AnyCodable]?
}
struct TableCell: Codable {
  let startIndex: Int?; let endIndex: Int?
  let content: [StructuralElement]; let tableCellStyle: [String: AnyCodable]?
}
struct TableOfContents: Codable { let content: [StructuralElement] }
```

`AnyCodable` = any helper you already use for free-form JSON dictionaries (`documentStyle`, `namedStyles`, color maps, etc. are returned as nested objects but are not load-bearing for editing text). For text reading/writing you only need `body.content[].paragraph.elements[].textRun.content`.

The full document object:

```swift
struct GDoc: Codable {
  let documentId: String
  let title: String
  let body: DocBody?
  let revisionId: String
  let suggestionsViewMode: String?       // "DEFAULT_FOR_CURRENT_ACCESS"
  let documentStyle: [String: AnyCodable]?
  let namedStyles: [String: AnyCodable]?
  let lists: [String: AnyCodable]?
  let inlineObjects: [String: AnyCodable]?
  let headers: [String: AnyCodable]?
  let footers: [String: AnyCodable]?
  let footnotes: [String: AnyCodable]?
  let namedRanges: [String: AnyCodable]?
  let positionedObjects: [String: AnyCodable]?
}
```

**Id formats.** `documentId` is a 32-char lowercase hex string (uuid4 with dashes stripped), e.g. `4f9c2a1b8e7d4a6cb0f1e2d3c4b5a6f7`. `revisionId` is an 8-char hex; document **revision** records use `rev_<revisionId>`. Never assume a fixed id — get it from `/_admin/state` or from a create response.

---

## Operation 1 — Get a document (full body / content)

**`GET /v1/documents/{documentId}`**

- **Path param:** `documentId` (string, required).
- **Query params:** none.
- **Body:** none.
- **Identity:** `X-Env-0-Gdoc-User` header (optional). The caller must be the **owner** or have **any** permission (reader/commenter/writer/owner) on the doc, otherwise `404` (access failures are reported as `404`, not `403`, on read).
- **Response `200`:** the full `GDoc` object above.

Realistic example response (a short two-paragraph doc):

```json
{
  "documentId": "4f9c2a1b8e7d4a6cb0f1e2d3c4b5a6f7",
  "title": "Q3 Planning Notes",
  "body": {
    "content": [
      {
        "endIndex": 1,
        "sectionBreak": {
          "sectionStyle": {
            "columnSeparatorStyle": "NONE",
            "contentDirection": "LEFT_TO_RIGHT",
            "sectionType": "CONTINUOUS"
          }
        }
      },
      {
        "startIndex": 1,
        "endIndex": 19,
        "paragraph": {
          "elements": [
            {
              "startIndex": 1,
              "endIndex": 19,
              "textRun": {
                "content": "Q3 Planning Notes\n",
                "textStyle": {}
              }
            }
          ],
          "paragraphStyle": {
            "namedStyleType": "NORMAL_TEXT",
            "direction": "LEFT_TO_RIGHT"
          }
        }
      },
      {
        "startIndex": 19,
        "endIndex": 53,
        "paragraph": {
          "elements": [
            {
              "startIndex": 19,
              "endIndex": 53,
              "textRun": {
                "content": "Owner: Alex Thompson (CTO)\n",
                "textStyle": {}
              }
            }
          ],
          "paragraphStyle": {
            "namedStyleType": "NORMAL_TEXT",
            "direction": "LEFT_TO_RIGHT"
          }
        }
      }
    ]
  },
  "revisionId": "a1b2c3d4",
  "suggestionsViewMode": "DEFAULT_FOR_CURRENT_ACCESS",
  "documentStyle": {
    "background": { "color": {} },
    "pageNumberStart": 1,
    "marginTop": { "magnitude": 72, "unit": "PT" },
    "marginBottom": { "magnitude": 72, "unit": "PT" },
    "marginRight": { "magnitude": 72, "unit": "PT" },
    "marginLeft": { "magnitude": 72, "unit": "PT" },
    "pageSize": {
      "height": { "magnitude": 792, "unit": "PT" },
      "width": { "magnitude": 612, "unit": "PT" }
    },
    "marginHeader": { "magnitude": 36, "unit": "PT" },
    "marginFooter": { "magnitude": 36, "unit": "PT" },
    "useCustomHeaderFooterMargins": true,
    "documentFormat": { "documentMode": "PAGES" }
  },
  "namedStyles": {
    "styles": [
      { "namedStyleType": "NORMAL_TEXT", "textStyle": { "...": "..." }, "paragraphStyle": { "...": "..." } },
      { "namedStyleType": "HEADING_1", "textStyle": { "fontSize": { "magnitude": 20, "unit": "PT" } }, "paragraphStyle": { "...": "..." } }
    ]
  }
}
```

To **read the document's text** on the client: concatenate every `body.content[].paragraph?.elements[].textRun?.content` (each paragraph already ends in `\n`). For an empty doc the body is a `sectionBreak` plus one paragraph whose single `textRun.content` is `"\n"`.

---

## Operation 2 — Create a document

**`POST /v1/documents`**

- **Path/query params:** none.
- **Request body JSON:**
  ```json
  { "title": "My new doc" }
  ```
  | field | type | required | default |
  |-------|------|----------|---------|
  | `title` | string | no | `"Untitled document"` |
  ```swift
  struct CreateDocRequest: Codable { let title: String }
  ```
- **Identity:** `X-Env-0-Gdoc-User` header (optional). The created doc is **owned** by the resolved user.
- **Response `200`:** the full `GDoc` object (same shape as Get) for the newly created, empty document. The server generates `documentId` and `revisionId`, seeds `documentStyle` + `namedStyles`, and sets the body to an empty body (`sectionBreak` + one empty `"\n"` paragraph). It also writes an initial revision record (`rev_<revisionId>`).

Realistic example response:

```json
{
  "documentId": "0a1b2c3d4e5f60718293a4b5c6d7e8f9",
  "title": "My new doc",
  "body": {
    "content": [
      {
        "endIndex": 1,
        "sectionBreak": {
          "sectionStyle": {
            "columnSeparatorStyle": "NONE",
            "contentDirection": "LEFT_TO_RIGHT",
            "sectionType": "CONTINUOUS"
          }
        }
      },
      {
        "startIndex": 1,
        "endIndex": 2,
        "paragraph": {
          "elements": [
            {
              "startIndex": 1,
              "endIndex": 2,
              "textRun": { "content": "\n", "textStyle": {} }
            }
          ],
          "paragraphStyle": {
            "namedStyleType": "NORMAL_TEXT",
            "direction": "LEFT_TO_RIGHT"
          }
        }
      }
    ]
  },
  "revisionId": "9f8e7d6c",
  "suggestionsViewMode": "DEFAULT_FOR_CURRENT_ACCESS",
  "documentStyle": { "...": "as in Get" },
  "namedStyles": { "...": "as in Get" }
}
```

Note: the real Google API ignores any `body` you send to create and starts empty — this mock does the same (only `title` is read from the request).

---

## Operation 3 — Save / update document content

There are **two distinct write paths**. For an iOS client the simplest is path B (the web-editor save), but the canonical Google-Docs path is A.

### A. `POST /v1/documents/{documentId}:batchUpdate`  (canonical, structured)

Note the literal `:batchUpdate` suffix on the path (colon, not a slash).

- **Path param:** `documentId` (string, required).
- **Identity:** `X-Env-0-Gdoc-User` header (optional). Caller must be **owner** or have **`writer`** role; reader/commenter → `403`, no access → `404`.
- **Request body JSON:**
  ```json
  {
    "requests": [
      { "insertText": { "location": { "index": 1 }, "text": "Hello world\n" } },
      { "replaceAllText": { "containsText": { "text": "foo", "matchCase": true }, "replaceText": "bar" } }
    ],
    "writeControl": { "requiredRevisionId": "a1b2c3d4" }
  }
  ```
  - `requests` is an array of request objects; each object has **exactly one** key naming the operation. `writeControl` is optional and currently **not enforced** (the server always applies and bumps the revision).
  - Common request shapes the mock implements (field names exact):
    - `insertText`: `{ "location": {"index": Int}, "text": String }`
    - `deleteContentRange`: `{ "range": {"startIndex": Int, "endIndex": Int} }`
    - `replaceAllText`: `{ "containsText": {"text": String, "matchCase": Bool}, "replaceText": String }` → reply `{"replaceAllText": {"occurrencesChanged": Int}}`
    - `updateTextStyle`: `{ "range": {...}, "textStyle": {...}, "fields": String }`
    - `updateParagraphStyle`: `{ "range": {...}, "paragraphStyle": {...}, "fields": String }`
    - `createParagraphBullets` / `deleteParagraphBullets`: `{ "range": {...}, "bulletPreset": String }`
    - `insertTable`, `insertInlineImage`, `insertPageBreak`, `createHeader`, `createFooter`, `createFootnote`, `createNamedRange`, `addDocumentTab`, etc. (full set: insert/delete/merge table ops, named ranges, tabs, equation, TOC, positioned objects, section/document style, `insertPerson`).
  - To **insert text at the end**, use the index just before the final paragraph's trailing newline. To **replace the whole body**, you typically `deleteContentRange` from `startIndex:1` to the last index, then `insertText` at index `1` — or just use path B below.
- **Response `200`** (`BatchUpdateDocumentResponse`):
  ```json
  {
    "documentId": "4f9c2a1b8e7d4a6cb0f1e2d3c4b5a6f7",
    "replies": [
      {},
      { "replaceAllText": { "occurrencesChanged": 3 } }
    ],
    "writeControl": { "requiredRevisionId": "b2c3d4e5" }
  }
  ```
  - `replies` is parallel to `requests` (one entry per request; `{}` when the op has no reply payload).
  - `writeControl.requiredRevisionId` is the **new** revision id after the update.
  ```swift
  struct BatchUpdateRequest: Codable { let requests: [[String: AnyCodable]] }
  struct BatchUpdateResponse: Codable {
    let documentId: String
    let replies: [[String: AnyCodable]]
    let writeControl: WriteControl?
  }
  struct WriteControl: Codable { let requiredRevisionId: String? }
  ```
- The response does **not** include the updated body — call Get again to re-read content.

### B. `POST /doc/{document_id}/save`  (web-editor save — simplest full-content overwrite)

This is the human web-UI route (under root, **not** `/v1`). It is the easiest "set the whole document text" call and requires **no permission check** (any caller; always exempt from auth).

- **Path param:** `document_id` (string, required).
- **Request body JSON:**
  ```json
  { "content": "Line one\nLine two\n\nNew paragraph", "format": "text" }
  ```
  | field | type | required | default | notes |
  |-------|------|----------|---------|-------|
  | `content` | string | yes | — | plain text (or HTML if `format:"html"`) |
  | `format` | string | no | `"text"` | `"text"` or `"html"` |
  - `format:"text"`: double newline (`\n\n`) = paragraph break; single newline kept within paragraph. Empty content → empty body.
  - `format:"html"`: parses `<p>`, `<h1>`–`<h6>`, `<div>`, `<ul>/<ol>/<li>`, inline `<b><i><u><s><span style=...>`.
  ```swift
  struct SaveRequest: Codable { let content: String; let format: String } // format: "text" | "html"
  ```
- **Response `200`:**
  ```json
  { "status": "ok", "modified_time": "2026-06-20T14:32:01.123456+00:00" }
  ```
  ```swift
  struct SaveResponse: Codable { let status: String; let modifiedTime: String
    enum CodingKeys: String, CodingKey { case status; case modifiedTime = "modified_time" } }
  ```
- **Not found:** `404` with body `{"error": "not found"}` (note: this route uses a *plain* error body, NOT the Google envelope).
- This call rewrites the entire body, bumps `revisionId`, and adds a revision record.

---

## Operation 4 — List documents

**There is no JSON/REST "list documents" endpoint.** The only document-listing surfaces are:

1. **`GET /_admin/state`** — the authoritative way to enumerate documents over JSON (see Health/admin above). Iterate `users.<userId>.documents[]`; each element is the document object (`id`, `title`, `body`, styles maps, `revisionId`, `suggestionsViewMode`, `createdTime`, `modifiedTime`). This lists docs grouped by owner and is intended for evaluation tooling, but it is a stable JSON contract an iOS client can use to discover document ids/titles.
2. **`GET /`** — the human web UI, which returns **HTML** (a Google-Drive-style document list, newest first, limited to 100), not JSON. Not usable as a data API.

(The codebase defines an unused `DocumentListSchema` `{ "documents": [...], "count": Int }`, but **no route serves it** — do not rely on it.)

For a mobile client that needs a document picker, query `GET /_admin/state` and read titles/ids from `users.<userId>.documents`. Per-document metadata available there: `id`, `title`, `revisionId`, `createdTime`, `modifiedTime`, plus full `body`.

```swift
struct AdminState: Codable { let users: [String: AdminUser]; let timestamp: String }
struct AdminUser: Codable {
  let user: AdminUserInfo
  let documents: [GDocFull]   // each like GDoc but with createdTime/modifiedTime, id (not documentId)
}
struct AdminUserInfo: Codable { let id: String; let email: String; let displayName: String }
```

Note the field-name difference: in `/_admin/state` the document key is **`id`** (and includes `createdTime`/`modifiedTime`), whereas the `/v1/documents/...` API responses use **`documentId`** and omit the timestamps.

---

## Seeded reference values (for testing the client)

- Primary user: id `user_0`, email `alex@nexusai.com`, display name `Alex Thompson`. This is the default identity when `X-Env-0-Gdoc-User` is omitted.
- Other seeded collaborators (domain `nexusai.com`): `sarah.chen@`, `marcus.johnson@`, `priya.patel@`, `tom.wilson@`, `elena.rodriguez@`, `david.kim@`, `rachel.green@`; plus personal contacts `linda.thompson@gmail.com`, `jake.morrison@gmail.com`.
- `suggestionsViewMode` default: `"DEFAULT_FOR_CURRENT_ACCESS"`. Default font: Arial 11pt. Default page: 612×792 PT with 72 PT margins.