I have all the concrete values. The default first user is `user1` / `alex@nexusai.com` / "Alex Chen". Now I have enough to write the complete spec.

# Mock Gmail API — Mobile Client Spec

This is a FastAPI mock of the Gmail REST API. It mirrors Google's wire format closely (same paths, field names, base64url message bodies, sparse responses), so an iOS client can point at this server instead of `googleapis.com` with no payload changes. Field names below are the EXACT JSON keys.

## Base URL / Port

- Port: **9001**, declared in `/home/liu.10379/env-0/config.toml` (`[gmail] port = 9001`).
- Env var: **`GMAIL_URL`** (e.g. `http://localhost:9001`).
- All Gmail endpoints are prefixed with **`/gmail/v1`**. Full example: `GET http://localhost:9001/gmail/v1/users/me/threads`.
- Admin/health endpoints are at the root (no prefix): `/health`, `/_admin/*`.

## Auth

- **By default the mock ignores auth entirely.** No `Authorization` header or token is required or checked. You can call every endpoint anonymously.
- User identity (the default) resolves in this order (`resolve_user_id` in `api/deps.py`):
  1. `userId` path param if it is not the literal `"me"` (must match a real user id, else 404).
  2. If `userId == "me"`: the optional header **`X-Mock-Gmail-User`** (matched against user id OR email).
  3. Fallback: the **first user in the DB** (with default seed that is id `user1`, email `alex@nexusai.com`).
- So for a single-mailbox client, just use **`me`** as `userId` everywhere and send no auth.
- Auth is only enforced when the server is started with env `AUTH_ENABLED=1` (optional, off in normal task runs). In that mode it expects an OAuth2 Bearer token (`Authorization: Bearer <jwt>`) whose `sub`/`email` maps to a local user, and per-route OAuth scopes apply (see `auth_scopes.py`). Naming a `userId` other than the token's subject yields a `403` with body `{"error": {"code": 403, "status": "PERMISSION_DENIED", "message", "authenticated_user", "requested_user"}}`. **If you don't set `AUTH_ENABLED`, none of this applies.**

## Error format

Non-2xx responses use Google's envelope (HTTPException handler in `api/app.py`):

```json
{
  "error": {
    "code": 404,
    "message": "Thread 'abc123' not found",
    "status": "NOT_FOUND",
    "errors": [{ "message": "Thread 'abc123' not found", "domain": "global", "reason": "notFound" }]
  }
}
```

Pydantic body-validation failures are remapped to `400` with the same envelope (`status: "INVALID_ARGUMENT"`, `reason: "required"`), not `422`.

## `/health`

`GET /health` → `200`:
```json
{ "status": "ok" }
```

## `/_admin/state` (brief)

`GET /_admin/state` → full world dump (used by graders; useful for the client to discover real ids in dev). Shape:

```json
{
  "users": {
    "user1": {
      "user": { "id": "user1", "email": "alex@nexusai.com", "displayName": "Alex Chen", "historyId": 1 },
      "messages": [
        {
          "id": "a1b2c3d4e5f6a7b8", "threadId": "f0e1d2c3b4a59687",
          "sender": "Jordan Rivera <colleague@example.com>", "to": "alex@nexusai.com",
          "cc": "", "subject": "Q3 planning", "snippet": "Hey, can we sync...",
          "body": "Hey, can we sync on Q3...", "bodyHtml": "",
          "internalDate": "2026-06-18T14:32:00", "isRead": false, "isStarred": false,
          "isTrash": false, "isSpam": false, "isDraft": false, "isSent": false,
          "labelIds": ["INBOX"], "messageIdHeader": "<...@gmail.local>",
          "inReplyTo": "", "references": ""
        }
      ],
      "threads": [{ "id": "f0e1d2c3b4a59687", "snippet": "Hey, can we sync...", "historyId": 1 }],
      "labels": [{ "id": "INBOX", "name": "INBOX", "type": "system" }],
      "drafts": [{ "id": "...", "messageId": "..." }],
      "filters": [], "contacts": [], "sendAs": [],
      "forwardingAddresses": [], "delegates": []
    }
  },
  "timestamp": "2026-06-20T10:00:00.000000"
}
```
Note: keys in `/_admin/state` use **camelCase booleans** (`isRead`, `bodyHtml`) and differ from the public API field names — it is a debug/grading view, not the client contract. Use the `/gmail/v1` endpoints below for the app.

---

# Operations

Notes that apply to all of them:
- Use `userId = "me"` for the single signed-in mailbox.
- IDs are opaque hex strings, 16 hex chars (e.g. `a1b2c3d4e5f6a7b8`) for messages/threads/drafts; user-created label ids look like `Label_ab12cd34`; system label ids are fixed strings (`INBOX`, `SENT`, `STARRED`, `UNREAD`, `TRASH`, `SPAM`, `DRAFT`, `IMPORTANT`, `CHAT`, `CATEGORY_PERSONAL`/`SOCIAL`/`PROMOTIONS`/`UPDATES`/`FORUMS`).
- Pagination: `pageToken` and `nextPageToken` are **stringified integer offsets** (e.g. `"100"`), NOT opaque cursors. `nextPageToken` is **omitted** when there is no next page.
- Sparse responses: list endpoints **omit** the items key entirely (no `threads`/`messages`/`drafts` key) when the result is empty — only `resultSizeEstimate` is guaranteed. Make these Swift fields optional.

---

## 1. List threads (with `q` search)

**`GET /gmail/v1/users/{userId}/threads`**

Query params:
| param | type | default | notes |
|---|---|---|---|
| `q` | string | — | Gmail search syntax (see below). |
| `maxResults` | int | 100 | 1–500. |
| `pageToken` | string | — | integer offset as string. |
| `labelIds` | string (repeatable or comma-separated) | — | e.g. `labelIds=INBOX` or `labelIds=INBOX,UNREAD`. |
| `includeSpamTrash` | bool | false | When false, trash/spam threads are excluded. |

`q` search operators supported: `from:`, `to:`, `subject:`, `label:`, `is:` (`unread`/`read`/`starred`/`important`), `in:` (`inbox`/`sent`/`trash`/`spam`/`drafts`), `category:`, `after:`/`before:` (YYYY/MM/DD), `older_than:`/`newer_than:` (e.g. `30d`,`2m`,`1y`), `has:attachment`. Bare words match subject OR body OR sender (case-insensitive substring). Values may be quoted (`subject:"weekly report"`).

**Response (200):** thread stubs only (no messages). `threads`/`nextPageToken` omitted when absent.
```json
{
  "resultSizeEstimate": 42,
  "threads": [
    { "id": "f0e1d2c3b4a59687", "snippet": "Hey, can we sync on Q3 planning before...", "historyId": "1" },
    { "id": "9a8b7c6d5e4f3021", "snippet": "Your invoice for May is ready", "historyId": "1" }
  ],
  "nextPageToken": "100"
}
```
Field types: `resultSizeEstimate` Int; `threads` `[Thread]?`; `nextPageToken` `String?`. Each thread: `id` String, `snippet` String, `historyId` String (note: **string**, not int).

---

## 2. Get thread + its messages

**`GET /gmail/v1/users/{userId}/threads/{threadId}`**

Query params: `format` = `full` (default) | `metadata` | `minimal` | `raw`.

**Response (200):** Note — `threads.get` returns **no `snippet`** key at the top level (only `id`, `historyId`, `messages`). Messages are ordered oldest→newest by `internalDate`.

```json
{
  "id": "f0e1d2c3b4a59687",
  "historyId": "1",
  "messages": [
    {
      "id": "a1b2c3d4e5f6a7b8",
      "threadId": "f0e1d2c3b4a59687",
      "labelIds": ["INBOX", "UNREAD"],
      "snippet": "Hey, can we sync on Q3 planning before...",
      "historyId": "1",
      "internalDate": "1750257120000",
      "sizeEstimate": 412,
      "payload": {
        "partId": "",
        "mimeType": "text/plain",
        "filename": "",
        "headers": [
          { "name": "From", "value": "Jordan Rivera <colleague@example.com>" },
          { "name": "To", "value": "alex@nexusai.com" },
          { "name": "Subject", "value": "Q3 planning" },
          { "name": "Date", "value": "Wed, 18 Jun 2026 14:32:00 +0000" },
          { "name": "MIME-Version", "value": "1.0" }
        ],
        "body": { "size": 256, "data": "SGV5LCBjYW4gd2Ugc3luYyBvbiBRMy4uLg" }
      }
    }
  ]
}
```

Message object fields (the full `MessageSchema`; **absent fields are omitted, never null**):
| field | type | notes |
|---|---|---|
| `id` | String | message id |
| `threadId` | String | |
| `labelIds` | [String] | computed; includes derived `UNREAD`/`STARRED`/`TRASH`/`SPAM`/`DRAFT`/`SENT` plus explicit labels like `INBOX`, `IMPORTANT`, `Label_xxx` |
| `snippet` | String? | first ~200 chars of plain body |
| `historyId` | String? | string form of an int |
| `internalDate` | String? | **epoch milliseconds as a string**, e.g. `"1750257120000"` |
| `sizeEstimate` | Int? | bytes |
| `payload` | MessagePart? | present for `full`/`metadata`; omitted for `minimal`/`raw` |
| `raw` | String? | present only for `format=raw`; base64url of the full RFC2822 message |

`MessagePart` (recursive):
| field | type | notes |
|---|---|---|
| `partId` | String | `""` for root, `"0"`,`"1"`… for children |
| `mimeType` | String | e.g. `text/plain`, `multipart/alternative`, `multipart/mixed` |
| `filename` | String | `""` unless attachment |
| `headers` | [Header] | `[{name,value}]` |
| `body` | MessagePartBody | |
| `parts` | [MessagePart]? | present only for multipart; omitted otherwise |

`MessagePartBody`:
| field | type | notes |
|---|---|---|
| `attachmentId` | String? | present only for attachment parts |
| `size` | Int | byte size (0 for container parts) |
| `data` | String? | **base64url (no padding)** of the UTF-8 body text; omitted for `format=metadata` and for container/attachment parts |

Payload shape by content: plain-only → root part is `text/plain` with `body.data`. Plain+HTML → root `multipart/alternative` (`body.size=0`, no data) with `parts[0]`=text/plain(partId `"0"`), `parts[1]`=text/html(partId `"1"`). With attachments → root `multipart/mixed`. To get the body text: base64url-decode `payload.body.data` (plain) or walk `parts` for the `text/plain`/`text/html` part. base64url decode = standard base64url, then re-add `=` padding to a multiple of 4 (the server strips padding).

`format=metadata` returns a trimmed payload: only `{ "mimeType", "headers" }` (no `body`, no `parts`).

---

## 3. List labels

**`GET /gmail/v1/users/{userId}/labels`**

No query params.

**Response (200):** In the **list** response, counts and visibility/color fields are **omitted** for labels that don't have them (system labels are sparse). `null` fields are dropped.

```json
{
  "labels": [
    { "id": "INBOX", "name": "INBOX", "type": "system" },
    { "id": "SENT", "name": "SENT", "type": "system" },
    { "id": "STARRED", "name": "STARRED", "type": "system" },
    { "id": "UNREAD", "name": "UNREAD", "type": "system" },
    { "id": "IMPORTANT", "name": "IMPORTANT", "type": "system", "messageListVisibility": "hide", "labelListVisibility": "labelHide" },
    { "id": "Label_ab12cd34", "name": "Receipts", "type": "user", "messageListVisibility": "show", "labelListVisibility": "labelShow", "color": { "backgroundColor": "#16a765", "textColor": "#ffffff" } }
  ]
}
```

`LabelSchema` fields:
| field | type | notes |
|---|---|---|
| `id` | String | |
| `name` | String | |
| `type` | String | `"system"` or `"user"` |
| `messageListVisibility` | String? | `show`/`hide`; omitted on many system labels |
| `labelListVisibility` | String? | `labelShow`/`labelHide`; omitted similarly |
| `messagesTotal` | Int? | **omitted in list response**; present only on `labels.get` / patch |
| `messagesUnread` | Int? | same |
| `threadsTotal` | Int? | same |
| `threadsUnread` | Int? | same |
| `color` | LabelColor? | `{ "backgroundColor": String?, "textColor": String? }`; omitted when no color set |

(For per-label counts, `GET /gmail/v1/users/{userId}/labels/{labelId}` returns the same schema **with** the `*Total`/`*Unread` ints populated.)

---

## 4. Modify message labels (star / read / unread / trash)

**`POST /gmail/v1/users/{userId}/messages/{messageId}/modify`**

Request body (`MessageModifyRequest`):
```json
{ "addLabelIds": ["STARRED"], "removeLabelIds": ["UNREAD"] }
```
Both fields are `[String]` and optional (default `[]`).

Semantics (the system labels map onto boolean flags server-side):
- **Star:** `addLabelIds: ["STARRED"]`; **unstar:** `removeLabelIds: ["STARRED"]`.
- **Mark read:** `removeLabelIds: ["UNREAD"]`; **mark unread:** `addLabelIds: ["UNREAD"]`.
- **Trash:** `addLabelIds: ["TRASH"]` (or use the dedicated `/trash` endpoint below). **Untrash:** `removeLabelIds: ["TRASH"]`.
- Any other label id (e.g. `IMPORTANT`, `INBOX`, a `Label_xxx`) is added/removed as an explicit label. Removing `INBOX` archives the message.

**Response (200):** the **minimal** message (`MessageMinimalSchema`), not the full object:
```json
{ "id": "a1b2c3d4e5f6a7b8", "threadId": "f0e1d2c3b4a59687", "labelIds": ["INBOX", "STARRED"] }
```
Fields: `id` String, `threadId` String, `labelIds` [String]. `404` if the message id doesn't exist for this user.

Dedicated convenience endpoints (same `MessageMinimalSchema` response):
- **`POST /gmail/v1/users/{userId}/messages/{messageId}/trash`** — sets trash, removes `INBOX`. No body.
- **`POST /gmail/v1/users/{userId}/messages/{messageId}/untrash`** — clears trash (does **not** restore `INBOX`). No body.

Thread-level equivalent (applies to every message in the thread): **`POST /gmail/v1/users/{userId}/threads/{threadId}/modify`** with the same `{addLabelIds, removeLabelIds}` body — but this returns the **full thread** (`ThreadSchema`: `{id, historyId, snippet, messages:[MessageSchema]}`), not a minimal message.

---

## 5. Compose + send a message

**`POST /gmail/v1/users/{userId}/messages/send`**

Request body (`MessageSendRequest`):
```json
{ "raw": "<base64url RFC2822>", "threadId": "f0e1d2c3b4a59687" }
```
| field | type | notes |
|---|---|---|
| `raw` | String (**required**) | base64url-encoded (no padding) full RFC2822 message. Recipients/subject/body are parsed FROM this — there are no separate `to`/`subject` body fields. |
| `threadId` | String? | optional; omit to start a new thread, set to reply within an existing thread |

Building `raw`: construct a standard RFC2822 message and base64url-encode it (strip `=` padding). Minimal example to encode:
```
To: colleague@example.com
Subject: Re: Q3 planning
Content-Type: text/plain; charset="UTF-8"

Sounds good — let's meet Thursday.
```
The server overrides the `From` header with the authenticated user's address. Parsed headers used: `To`, `Cc`, `Bcc`, `Subject`, `Date`, `Message-ID`, `In-Reply-To`, `References`. For multipart, the server reads the first `text/plain` and first `text/html` parts. If the recipient is another local user, a copy is delivered to their inbox.

**Response (200):** minimal message (`MessageMinimalSchema`); the sent message gets labels `SENT` and `INBOX`:
```json
{ "id": "c4d5e6f7a8b90123", "threadId": "f0e1d2c3b4a59687", "labelIds": ["SENT", "INBOX"] }
```

---

## 6. Create draft

**`POST /gmail/v1/users/{userId}/drafts`**

Request body (`DraftCreateRequest`) — note the message is **nested** under `message`:
```json
{ "message": { "raw": "<base64url RFC2822>", "threadId": null } }
```
| field | type | notes |
|---|---|---|
| `message.raw` | String (**required**) | base64url RFC2822, same encoding as send |
| `message.threadId` | String? | optional thread to attach to |

**Response (201 Created):** `DraftSchema` with the message in **minimal** form (id/threadId/labelIds; the draft message carries the `DRAFT` label):
```json
{
  "id": "d7e8f9a0b1c2d3e4",
  "message": { "id": "9f8e7d6c5b4a3210", "threadId": "1122334455667788", "labelIds": ["DRAFT"] }
}
```
`DraftSchema`: `id` String; `message` is a message object — **minimal on create** (`{id, threadId, labelIds}`), but **full `MessageSchema`** when later fetched via `GET /drafts/{draftId}` (with `payload`, `snippet`, etc.). Make the Swift `message` type able to decode both (all full-only fields optional).

Related draft endpoints (for completeness):
- `GET /gmail/v1/users/{userId}/drafts` → `{ "resultSizeEstimate": Int, "drafts"?: [{ "id": String, "message": { "id": String, "threadId": String } }], "nextPageToken"?: String }` (`drafts` omitted when empty). Supports `q`, `maxResults`, `pageToken`, `includeSpamTrash`.
- `GET /gmail/v1/users/{userId}/drafts/{draftId}?format=full` → full `DraftSchema`.
- `POST /gmail/v1/users/{userId}/drafts/send` with body `{ "id": "<draftId>" }` → sends the draft, returns full `MessageSchema`.

---

## Suggested Swift Codable shapes

```swift
struct ThreadList: Codable { let resultSizeEstimate: Int; let threads: [ThreadStub]?; let nextPageToken: String? }
struct ThreadStub: Codable { let id: String; let snippet: String; let historyId: String? }

struct ThreadDetail: Codable { let id: String; let historyId: String?; let messages: [GMessage] }

struct GMessage: Codable {
    let id: String; let threadId: String
    let labelIds: [String]?
    let snippet: String?; let historyId: String?
    let internalDate: String?            // epoch ms as string
    let sizeEstimate: Int?
    let payload: MessagePart?
    let raw: String?
}
struct MessagePart: Codable {
    let partId: String?; let mimeType: String?; let filename: String?
    let headers: [Header]?; let body: PartBody?; let parts: [MessagePart]?
}
struct Header: Codable { let name: String; let value: String }
struct PartBody: Codable { let attachmentId: String?; let size: Int?; let data: String? }

struct LabelList: Codable { let labels: [GLabel] }
struct GLabel: Codable {
    let id: String; let name: String; let type: String
    let messageListVisibility: String?; let labelListVisibility: String?
    let messagesTotal: Int?; let messagesUnread: Int?
    let threadsTotal: Int?; let threadsUnread: Int?
    let color: LabelColor?
}
struct LabelColor: Codable { let backgroundColor: String?; let textColor: String? }

struct ModifyLabelsRequest: Codable { let addLabelIds: [String]; let removeLabelIds: [String] }
struct MinimalMessage: Codable { let id: String; let threadId: String; let labelIds: [String]? }

struct SendRequest: Codable { let raw: String; let threadId: String? }
struct DraftCreateRequest: Codable { let message: SendRequest }   // {"message":{"raw":...}}
struct Draft: Codable { let id: String; let message: GMessage }    // message minimal on create, full on get
```

Source files referenced: `api/app.py` (mounting, errors, health, `/_admin`), `api/threads.py`, `api/messages.py`, `api/labels.py`, `api/drafts.py`, `api/schemas.py`, `api/mime.py` (base64url + payload tree), `api/deps.py` (`me`/userId resolution, no-auth default), `auth_scopes.py` / `api/auth_middleware.py` (auth only when `AUTH_ENABLED=1`), `models/message.py`, `models/label.py`, `models/user.py`, `state/snapshots.py` (`/_admin/state`), `config.toml` (port 9001 / `GMAIL_URL`).