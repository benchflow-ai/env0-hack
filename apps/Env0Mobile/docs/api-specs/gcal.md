I now have a complete picture. Note: seeded calendar ids are `<key>-<email>` (e.g. `primary-alex@nexusai.com`, `team-alex@nexusai.com`), while user-created calendars get `cal_<hex>` and events get `evt_<hex>`. The "respond/RSVP" operation is done via PATCH event updating the attendee's `responseStatus` (there is no dedicated RSVP endpoint — the real Google API also uses events.patch for this). I have all field names, types, and example values. Here is the spec.

---

# Mock Google Calendar (gcal) — Mobile HTTP API Spec

## Base URL / Port

- **Port:** `9003`
- **Env var:** `CALENDAR_URL` (e.g. `http://localhost:9003`)
- **API prefix:** all Calendar endpoints are mounted under `/calendar/v3`. So a full path is `{CALENDAR_URL}/calendar/v3/...`.
- Mirrors the real Google Calendar v3 wire format, so paths/JSON match `https://www.googleapis.com/calendar/v3/...`.

## Auth

- **Default: no auth.** The mock ignores `Authorization` entirely unless `AUTH_ENABLED` is set truthy (`1`/`true`/`yes`) in the server environment. In the default/benchmark config it is **off**, so you do **not** need a Bearer token.
- **Identity selection (auth disabled):** the acting user is resolved in this order:
  1. The `userId` path param (for `/users/{userId}/...` routes) — `me` means "resolve from header/first user".
  2. Header `X-Env-0-Gcal-User` or `X-Mock-Gcal-User`, whose value may be a **user id** OR an **email address** (e.g. `alex@nexusai.com`).
  3. Fallback: the **first user in the DB** (the seeded account owner, `alex@nexusai.com`).
  For routes without a `userId` param (events, freeBusy, calendars, acl), only steps 2–3 apply.
- **If `AUTH_ENABLED=1`:** a verified Bearer JWT is required on `/calendar/v3/*`. The token's `sub`/`email` maps to a local user; naming a different `userId` in the path raises a contract 403 with body `{"error":{"code":403,"status":"PERMISSION_DENIED","message":...,"authenticated_user":...,"requested_user":...}}`. Per-route OAuth scopes apply (`calendar.readonly`, `calendar.events`, `calendar.events.readonly`, `calendar.full`). Exempt prefixes: `/_admin`, `/health`, `/dev`, `/docs`, `/openapi.json`, `/mcp`, `/static`, and exact `/`.
- **Error envelope (all 4xx/5xx except auth 403):** Google-style:
```json
{ "error": { "code": 404, "message": "Event not found", "reason": "notFound", "status": "NOT_FOUND",
  "errors": [ { "message": "Event not found", "domain": "global", "reason": "notFound" } ] } }
```
Pydantic validation failures are remapped to `400` with `reason: "required"`.

## Health & State (admin)

- `GET /health` → `{"status": "ok"}`
- `GET /_admin/state` → full dump:
```json
{
  "users": {
    "usr_xxx": {
      "user": { "id": "usr_xxx", "email": "alex@nexusai.com", "displayName": "Alex Chen", "timezone": "UTC", "historyId": 1 },
      "calendars": [ { "id": "primary-alex@nexusai.com", "summary": "alex@nexusai.com", "description": "", "location": "", "timeZone": "UTC", "accessRole": "owner", "primary": true, "selected": true, "hidden": false, "summaryOverride": "", "autoAcceptInvitations": false, "colorId": "14" } ],
      "acls": [ { "id": "primary-alex@nexusai.com:user:alex@nexusai.com", "calendarId": "primary-alex@nexusai.com", "scopeType": "user", "scopeValue": "alex@nexusai.com", "role": "owner", "etag": "\"...\"" } ],
      "events": [ { "id": "evt_abc123", "calendarId": "team-alex@nexusai.com", "summary": "...", "description": "...", "location": "...", "status": "confirmed", "start": "2026-06-22T10:00:00+00:00", "end": "2026-06-22T12:00:00+00:00", "startIsDate": false, "endIsDate": false, "attendees": [ { "email": "sarah.kim@nexusai.com", "responseStatus": "needsAction" } ], "etag": "\"...\"", "iCalUID": "...@google.com", "sequence": 0, "recurrence": "[]", "recurringEventId": "", "originalStartTime": "", "created": "...", "updated": "..." } ]
    }
  },
  "timestamp": "2026-06-20T12:00:00+00:00"
}
```
- `GET /_admin/diff` → `{"users": {"<uid>": {"calendars": {added,updated,deleted}, "acls": {...}, "events": {...}}}}`.
- `GET /_admin/action_log` → `{"entries": [...], "count": N}`.

## ID & identity conventions (important)

- **Seeded calendar ids** are `"<key>-<owner_email>"`, e.g. `primary-alex@nexusai.com`, `team-alex@nexusai.com`, `product-alex@nexusai.com`. The primary calendar's `summary` is the owner's email (`alex@nexusai.com`).
- **User-created calendars** get id `"cal_<12 hex>"`; **created events** get id `"evt_<12 hex>"`.
- `calendarId` accepts the literal **`"primary"`** alias → resolves to the actor's primary calendar.
- `userId` accepts the literal **`"me"`** alias.
- **Recurring-event instance ids** look like `"<baseEventId>_YYYYMMDDTHHMMSSZ"` (e.g. `evt_abc123_20260622T100000Z`). Such ids are accepted by `GET .../events/{eventId}`.
- **iCalUID** of created events is `"<32 hex>@google.com"` unless you supply your own.
- **etags** are quoted MD5 strings, e.g. `"\"9f86d081...\""`.
- **Datetimes** are RFC3339 UTC with `Z` suffix on output (`2026-06-22T10:00:00Z`). Inputs accept `Z` or `+00:00`; naive datetimes are treated as UTC. All-day values use `date` (`"2026-06-22"`), no time.
- **No base64 anywhere** (unlike gmail) — all strings are plain text/JSON.
- **Pagination:** `nextPageToken` is a plain **integer offset as a string** (e.g. `"250"`). Pass it back as `pageToken`. `nextSyncToken` is an opaque MD5 string and is suppressed when incompatible filters (`q`, `timeMin/Max`, `singleEvents`, `orderBy`, `pageToken`) are used.

---

## 1. List calendars — `calendarList.list`

`GET /calendar/v3/users/{userId}/calendarList`

**Path:** `userId` — use `me`.
**Query params (all optional):**
| param | type | default |
|---|---|---|
| `maxResults` | int (1–250) | 100 |
| `pageToken` | string (numeric offset) | — |
| `minAccessRole` | string (`none`/`freeBusyReader`/`reader`/`writer`/`owner`) | — |
| `showHidden` | bool | false |
| `syncToken` | string | — |

Sorted primary-first, then by summary. Hidden calendars excluded unless `showHidden=true`.

**Response** (`calendar#calendarList`):
```json
{
  "kind": "calendar#calendarList",
  "etag": "\"a1b2c3\"",
  "items": [
    {
      "kind": "calendar#calendarListEntry",
      "etag": "\"d4e5f6\"",
      "id": "primary-alex@nexusai.com",
      "summary": "alex@nexusai.com",
      "timeZone": "UTC",
      "accessRole": "owner",
      "primary": true,
      "selected": true,
      "colorId": "14",
      "backgroundColor": "#039be5",
      "foregroundColor": "#ffffff",
      "conferenceProperties": { "allowedConferenceSolutionTypes": ["hangoutsMeet"] },
      "defaultReminders": [ { "method": "popup", "minutes": 10 } ],
      "notificationSettings": {
        "notifications": [
          { "type": "eventCreation", "method": "email" },
          { "type": "eventChange", "method": "email" },
          { "type": "eventCancellation", "method": "email" },
          { "type": "eventResponse", "method": "email" }
        ]
      }
    },
    {
      "kind": "calendar#calendarListEntry",
      "etag": "\"99aa\"",
      "id": "team-alex@nexusai.com",
      "summary": "NexusAI Engineering",
      "description": "Team rituals, sprint planning, and engineering meetings",
      "timeZone": "UTC",
      "accessRole": "owner",
      "selected": true,
      "colorId": "9",
      "backgroundColor": "#33b679",
      "foregroundColor": "#ffffff",
      "conferenceProperties": { "allowedConferenceSolutionTypes": ["hangoutsMeet"] },
      "dataOwner": "alex@nexusai.com"
    }
  ],
  "nextPageToken": null,
  "nextSyncToken": "7c4a8d09ca37..."
}
```

**`CalendarListEntry` fields** (response_model_exclude_none — fields are omitted when null):
- `kind`: `"calendar#calendarListEntry"` (const)
- `etag`: string
- `id`: string
- `summary`: string
- `timeZone`: string
- `accessRole`: string (`owner`/`reader`/`writer`/`freeBusyReader`/`none`)
- `primary`: bool — **present only when true** (omitted for non-primary)
- `selected`: bool? (present when true)
- `colorId`: string?
- `backgroundColor`: string? (hex)
- `foregroundColor`: string? (hex)
- `conferenceProperties`: `{ "allowedConferenceSolutionTypes": [string] }`
- `defaultReminders`: `[ { "method": string, "minutes": int } ]` — only on primary
- `notificationSettings`: `{ "notifications": [ { "type": string, "method": string } ] }` — only on primary
- `dataOwner`: string? — owner email, only on non-primary calendars
- `description`: string? (non-primary only, when non-empty)
- `location`: string?
- `summaryOverride`: string?
- `hidden`: bool? (present when true)
- `deleted`: bool?
- `autoAcceptInvitations`: bool? (present when true)

Note: For Swift Codable, declare every optional field as optional (`?`). `kind`, `etag`, `id`, `summary`, `timeZone`, `accessRole` are always present.

---

## 2. List events — `events.list`

`GET /calendar/v3/calendars/{calendarId}/events`

**Path:** `calendarId` — a calendar id or `primary`.
**Query params:**
| param | type | default | notes |
|---|---|---|---|
| `timeMin` | RFC3339 string | — | lower bound (event `end >= timeMin`) |
| `timeMax` | RFC3339 string | — | upper bound (event `start <= timeMax`); must be `> timeMin` |
| `maxResults` | int (1–2500) | 250 | |
| `pageToken` | string (numeric) | — | |
| `syncToken` | string | — | |
| `singleEvents` | bool | false | expands recurring masters into instances |
| `q` | string | — | substring match on summary/description |
| `orderBy` | string | — | `startTime` (default behavior) or `updated` |
| `showDeleted` | bool | false | include `status:"cancelled"` |

**Response** (`calendar#events`):
```json
{
  "kind": "calendar#events",
  "etag": "\"listetag\"",
  "summary": "NexusAI Engineering",
  "description": "Team rituals, sprint planning, and engineering meetings",
  "timeZone": "UTC",
  "updated": "2026-06-22T12:00:00Z",
  "accessRole": "owner",
  "defaultReminders": [ { "method": "popup", "minutes": 10 } ],
  "nextPageToken": null,
  "nextSyncToken": "a1b2c3...",
  "items": [ /* array of EventResource (see §3) */ ]
}
```
`EventListResponse` fields: `kind` (const `calendar#events`), `etag`, `summary`, `timeZone`, `items` (always present), `description` (default `""`), `updated` (string?), `accessRole` (string?), `defaultReminders` (`[{method,minutes}]`?), `nextPageToken` (string?), `nextSyncToken` (string?).

When `singleEvents=true`, recurring events appear as expanded instances (ids `evt_..._YYYYMMDDTHHMMSSZ`, with `recurringEventId` + `originalStartTime`, and `recurrence` omitted).

---

## 3. Get single event — `events.get`

`GET /calendar/v3/calendars/{calendarId}/events/{eventId}`

**Path:** `calendarId` (or `primary`), `eventId` (base `evt_...` id, or an instance id `evt_..._YYYYMMDDTHHMMSSZ`).
404 if not found.

**Response** (`calendar#event` = `EventResource`):
```json
{
  "kind": "calendar#event",
  "etag": "\"3858f62230ac3c91\"",
  "id": "evt_abc123def456",
  "status": "confirmed",
  "htmlLink": "https://www.google.com/calendar/event?eid=evt_abc123def456",
  "created": "2026-06-15T09:00:00Z",
  "updated": "2026-06-18T14:30:00Z",
  "summary": "Q2 Planning Kickoff",
  "description": "Finalize engineering priorities for Q2.",
  "location": "Zoom",
  "iCalUID": "f1e2d3c4b5a6@google.com",
  "sequence": 0,
  "start": { "dateTime": "2026-06-22T10:00:00Z", "timeZone": "UTC" },
  "end":   { "dateTime": "2026-06-22T12:00:00Z", "timeZone": "UTC" },
  "attendees": [
    { "email": "sarah.kim@nexusai.com",   "responseStatus": "accepted" },
    { "email": "marcus.rivera@nexusai.com","responseStatus": "needsAction" }
  ],
  "creator":   { "email": "alex@nexusai.com", "self": true },
  "organizer": { "email": "alex@nexusai.com", "self": true, "displayName": "NexusAI Engineering" },
  "reminders": { "useDefault": true },
  "eventType": "default"
}
```

**`EventResource` fields** (response_model_exclude_none):
- `kind`: `"calendar#event"` (const)
- `etag`: string
- `id`: string
- `status`: string (`confirmed` / `cancelled` / `tentative`)
- `htmlLink`: string (default `""`; form `https://www.google.com/calendar/event?eid=<id>`)
- `created`: RFC3339 string
- `updated`: RFC3339 string
- `summary`: string? (omitted if empty)
- `description`: string?
- `location`: string?
- `iCalUID`: string (always present)
- `sequence`: int (default 0; increments on each update/patch)
- `start`: `EventDateTime`
- `end`: `EventDateTime`
- `attendees`: `[EventAttendee]?` (omitted entirely when none)
- `creator`: `EventActor?`
- `organizer`: `EventActor?`
- `reminders`: `{ "useDefault": bool }?` (mock always returns `{"useDefault": true}`)
- `eventType`: string? (mock returns `"default"`)
- `recurrence`: `[string]?` (RRULE strings, e.g. `["RRULE:FREQ=WEEKLY;COUNT=12"]`)
- `recurringEventId`: string? (set on instances)
- `originalStartTime`: `EventDateTime?` (set on instances)

**`EventDateTime`:** `{ "dateTime": string?, "date": string?, "timeZone": string? }`
- Timed events: `dateTime` (RFC3339 `...Z`) + `timeZone`; `date` absent.
- All-day events: `date` (`"2026-06-22"`) only; `dateTime`/`timeZone` absent.

**`EventAttendee`:** `{ "email": string, "responseStatus": string (default "needsAction"), "self": bool?, "displayName": string?, "organizer": bool?, "optional": bool? }`. `responseStatus` ∈ `needsAction`/`accepted`/`declined`/`tentative`.

**`EventActor` (creator/organizer):** `{ "email": string, "self": bool?, "displayName": string? }`.

---

## 4. Create event — `events.insert`

`POST /calendar/v3/calendars/{calendarId}/events`

**Path:** `calendarId` (or `primary`).
**Request body** (`EventWriteRequest`):
```json
{
  "summary": "Design review",
  "description": "Walk through the new flows.",
  "location": "Meet Room A",
  "start": { "dateTime": "2026-06-25T15:00:00Z", "timeZone": "UTC" },
  "end":   { "dateTime": "2026-06-25T16:00:00Z", "timeZone": "UTC" },
  "attendees": [ { "email": "priya.sharma@nexusai.com" } ],
  "recurrence": ["RRULE:FREQ=WEEKLY;COUNT=4"],
  "iCalUID": null,
  "status": null
}
```
- `start` and `end` are **required** objects. `summary`/`description`/`location` default to `""`. `attendees`/`recurrence`/`iCalUID`/`status` optional.
- For all-day: `"start": {"date":"2026-06-25"}`, `"end": {"date":"2026-06-26"}`.
- **Validation:** `end` must be strictly after `start` (else 400). Missing both `dateTime` and `date` in a slot → 400.
- Defaults set by server: `status` → `"confirmed"`, `sequence` → 0, `iCalUID` → generated, id → `evt_<hex>`.

**Response:** a full `EventResource` (see §3), 200.

---

## 5. Update / Patch event — `events.update` / `events.patch`

Two variants:

### PATCH (partial) — `events.patch`
`PATCH /calendar/v3/calendars/{calendarId}/events/{eventId}`
**Body** (`EventPatchRequest`) — every field optional; only supplied fields change:
```json
{
  "summary": "Renamed meeting",
  "description": "...",
  "location": "...",
  "status": "confirmed",
  "start": { "dateTime": "2026-06-25T15:30:00Z" },
  "end":   { "dateTime": "2026-06-25T16:30:00Z" },
  "attendees": [ { "email": "priya.sharma@nexusai.com", "responseStatus": "accepted" } ],
  "recurrence": ["RRULE:FREQ=DAILY;COUNT=3"]
}
```

### PUT (full replace) — `events.update`
`PUT /calendar/v3/calendars/{calendarId}/events/{eventId}`
**Body** is the same shape as create (`EventWriteRequest`) — `start`/`end` **required**; unspecified scalar fields reset to defaults (`summary`/`description`/`location` → `""`).

Both: `sequence` increments, `updated` refreshes, etag recomputes, end-must-be-after-start enforced (400 otherwise). 404 if event not found in that calendar.
**Response:** full `EventResource`, 200.

---

## 6. Delete event — `events.delete`

`DELETE /calendar/v3/calendars/{calendarId}/events/{eventId}`

Hard-deletes the row (not a soft cancel). **Response: `204 No Content`, empty body.** 404 if not found.

---

## 7. Respond / RSVP to event

**There is no dedicated RSVP endpoint.** As in the real Google Calendar API, RSVP is performed with **`events.patch`** by rewriting the `attendees` array so the current user's attendee entry has the new `responseStatus`.

`PATCH /calendar/v3/calendars/{calendarId}/events/{eventId}`

**Body:**
```json
{
  "attendees": [
    { "email": "alex@nexusai.com",          "responseStatus": "accepted" },
    { "email": "sarah.kim@nexusai.com",      "responseStatus": "accepted" },
    { "email": "marcus.rivera@nexusai.com",  "responseStatus": "needsAction" }
  ]
}
```
Notes:
- `attendees` is **replaced wholesale** — include the full attendee list, not just the changed one. To change your own RSVP, fetch the event (§3), flip your entry's `responseStatus`, and PATCH the whole array.
- Valid `responseStatus`: `needsAction`, `accepted`, `declined`, `tentative`.
- The mock does not auto-stamp `self:true` on attendees you write; identify yourself by the owner email (`alex@nexusai.com`). The `self` flag appears on `creator`/`organizer` in responses.
- **Response:** full `EventResource` (the `attendees` array reflects the new statuses), 200.

---

## 8. FreeBusy — `freebusy.query`

`POST /calendar/v3/freeBusy`

**Request body** (`FreeBusyRequest`):
```json
{
  "timeMin": "2026-06-22T00:00:00Z",
  "timeMax": "2026-06-23T00:00:00Z",
  "timeZone": "UTC",
  "items": [ { "id": "primary" }, { "id": "team-alex@nexusai.com" } ],
  "groupExpansionMax": null,
  "calendarExpansionMax": null
}
```
- `timeMin`, `timeMax`, `items` required. `items` is a list of `{ "id": string }` (each id is a calendarId or `primary`). `timeMax` must be `> timeMin` (else 400).

**Response** (`calendar#freeBusy`):
```json
{
  "kind": "calendar#freeBusy",
  "timeMin": "2026-06-22T00:00:00Z",
  "timeMax": "2026-06-23T00:00:00Z",
  "calendars": {
    "primary": {
      "busy": [ { "start": "2026-06-22T10:00:00Z", "end": "2026-06-22T12:00:00Z" } ]
    },
    "team-alex@nexusai.com": {
      "errors": [ { "domain": "global", "reason": "notFound" } ],
      "busy": []
    }
  },
  "groups": null
}
```
- `calendars` is a **map keyed by the exact `id` string you passed in** (so if you sent `"primary"`, the key is `"primary"`, not the resolved calendar id).
- Each value: `{ "busy": [ { "start": RFC3339, "end": RFC3339 } ], "errors": [ {domain, reason} ]? }`. `errors` (e.g. `notFound` for an unknown/unauthorized calendar) is present only on failure; `busy` is always an array.
- Busy ranges are clamped to `[timeMin, timeMax]`, sorted ascending, and recurring events are expanded into individual busy slots. Cancelled events contribute nothing.

---

## Swift Codable notes

- Make every field marked `?` an optional. `response_model_exclude_none=True` means null fields are **absent from JSON**, so optionals decode cleanly.
- `kind` fields are constant discriminators; safe to decode as `String`.
- All datetimes are strings (RFC3339) — decode as `String` and parse with `ISO8601DateFormatter` (handle the `Z` and the all-day `date`-only form `yyyy-MM-dd` separately via `EventDateTime`).
- `EventDateTime` needs all three (`dateTime`, `date`, `timeZone`) optional; exactly one of `dateTime`/`date` is populated.
- `etag`/ids are opaque strings — never parse them. `nextPageToken` is a numeric string; pass it back verbatim as `pageToken`.