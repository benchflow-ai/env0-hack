# Mock Gmail API Notes

## Ground Truth

- **Official REST API spec**: https://developers.google.com/gmail/api/reference/rest
- **Discovery Document** (machine-readable schema): https://gmail.googleapis.com/$discovery/rest?version=v1
- **Per-resource specs**:
  - Messages: https://developers.google.com/gmail/api/reference/rest/v1/users.messages
  - Threads: https://developers.google.com/gmail/api/reference/rest/v1/users.threads
  - Labels: https://developers.google.com/gmail/api/reference/rest/v1/users.labels
  - Drafts: https://developers.google.com/gmail/api/reference/rest/v1/users.drafts
  - History: https://developers.google.com/gmail/api/reference/rest/v1/users.history
  - Settings: https://developers.google.com/gmail/api/reference/rest/v1/users.settings
- **Search query syntax**: https://developers.google.com/gmail/api/guides/filtering
- **Message format guide**: https://developers.google.com/gmail/api/guides/sending
- **Fixture source**: captured from a private Gmail test account.
- **Auth script**: `scripts/gmail_auth.py` (OAuth, saves `scripts/token.json`)
- **Fixture capture**: `scripts/capture_fixtures.py` → `tests/fixtures/real_gmail/`
- **Endpoint spec**: `tests/fixtures/gmail_api_spec.json`
- **Coverage map**: `tests/fixtures/mock_coverage.json`

### Reference Implementations

- **FlowCrypt** (github.com/nickyeoman/flowcrypt-browser): Mock Gmail server, 131 real exported JSON fixtures
- **Inbox Zero** (github.com/elie222/inbox-zero): 34 Gmail utility files, production usage patterns
- **gogcli**: Production CLI patterns covering Gmail API methods

---

## API Quirks (append-only, dated)

Discovered during golden fixture analysis on 2026-02-28. Each finding references a fixture in `tests/fixtures/real_gmail/`.

- **2026-02-28: Mutation responses are minimal.** `send`, `modify`, `trash`, `untrash` all return only `{id, threadId, labelIds}` — no snippet, no payload, no historyId. See `message_send_response.json`, `message_modify_response.json`.

- **2026-02-28: `format=raw` omits `payload` key entirely.** Not `payload: null` — the key is absent. See `message_get_raw.json`.

- **2026-02-28: `format=minimal` is very sparse.** Only `{id, threadId, labelIds, snippet, sizeEstimate, historyId, internalDate}`. No `payload`, no `raw`. See `message_get_minimal.json`.

- **2026-02-28: Empty list responses return `{}`.** Settings endpoints with no data return `{}`, not `{"filter": []}`. See `settings_filters_list.json`, `settings_forwarding_list.json`.

- **2026-02-28: Settings omit unset fields.** `autoForwarding` returns only `{"enabled": false}`, not all fields with defaults. `vacation` returns 3 of ~10 fields when disabled. See `settings_autoforwarding.json`, `settings_vacation.json`.

- **2026-02-28: System label visibility patterns.** SENT, INBOX, DRAFT, STARRED, UNREAD have NO visibility fields. IMPORTANT, TRASH, SPAM, CHAT, CATEGORY_* have `messageListVisibility: "hide"` and `labelListVisibility: "labelHide"`. See `labels_list.json`.

- **2026-02-28: CHAT label always exists.** With `messageListVisibility: "hide"`, `labelListVisibility: "labelHide"`. See `labels_list.json`.

- **2026-02-28: System labels have no counts.** `labels.list` does NOT include `messagesTotal`, `messagesUnread`, `threadsTotal`, `threadsUnread` for system labels. Only user labels include counts via `labels.get`. See `labels_list.json`.

- **2026-02-28: Delegates API requires domain-wide authority.** `settings.delegates.list` returns 403 for free Gmail accounts. Only works with Google Workspace.

- **2026-02-28: `format=full` payload tree has specific nesting rules.** Plain-only → single `text/plain` part. Plain+HTML → `multipart/alternative` with children. With attachments → `multipart/mixed` wrapping text part(s) + attachment parts. `partId` numbering: `"0"`, `"0.0"`, `"0.1"`, `"1"`. See `message_get_full.json`.

- **2026-02-28: `internalDate` is epoch milliseconds as a string.** Not an integer, not ISO 8601. `historyId` is sourced from the user's history counter. See `message_get_full.json`.

- **2026-02-28: Every user always has default settings resources.** Primary `SendAs` entry (their email), default `VacationSettings` (disabled), default `AutoForwarding` (disabled). Mock must seed these — they're not created on first access. See `settings_sendas_list.json`, `settings_vacation.json`, `settings_autoforwarding.json`.

---

## Intentionally Skipped

| Feature | Reason |
|---------|--------|
| Settings: CSE Identities (list, get, create) | Client-Side Encryption not relevant for agent testing |
| Settings: CSE Keypairs (list, get) | Client-Side Encryption not relevant for agent testing |
| Batch API (`POST /batch`) | Multi-request batching not needed for agent workflows |
| `fields` query parameter | Partial response not needed for agent testing |
| Rate limiting | Not relevant for mock |
| Watch/Push notifications | Implemented as no-ops; real would need Pub/Sub |

---

## Key Design Choices

- **Stateful mock, not replay**: Full CRUD with persistent SQLite, enabling multi-step agent workflows
- **Real-API send format**: Requires `{raw: base64url_rfc2822}` (matches real Gmail API)
- **Local delivery**: Messages sent between users in the system are delivered to recipient's inbox
- **Multi-user**: Resolved via `X-Mock-User-Id` header or path `userId`
- **Delegates accepted despite 403 on free Gmail**: Mock allows delegate operations for completeness
- **HTML snippets use plain text**: Real Gmail uses HTML entities (`&#39;`) in snippet field; mock uses plain text
- **Message format fidelity**:
  - **Send**: Requires `{raw: base64url_rfc2822}` (matches real Gmail API)
  - **Read (format=full)**: Proper nested `payload.parts[]` tree — plain only → single `text/plain`; plain+HTML → `multipart/alternative`; with attachments → `multipart/mixed`. `partId` numbering: `"0"`, `"0.0"`, `"0.1"`, `"1"`. Headers: From, To, Cc, Bcc, Subject, Date (RFC 2822), Message-ID, MIME-Version, In-Reply-To, References
  - **Read (format=raw)**: Base64url-encoded RFC 2822 in `raw` field, `payload` key omitted (not null)
  - **Read (format=metadata)**: Payload tree with headers but `body.data` omitted
  - **`historyId`**: Set on every message from `user.history_id`
  - **`internalDate`**: Epoch milliseconds string

---

## Open Questions

- **HTML entity encoding in snippets**: Real Gmail uses `&#39;` etc. in the `snippet` field. Our mock returns plain text. Low priority — unlikely to affect agent behavior.
- **Delegates fidelity**: Only testable with Google Workspace accounts (free Gmail returns 403). Mock accepts delegate operations for completeness but behavior is untested against real API.
- **`fields` parameter**: Gmail supports partial responses via `fields` query param. Not implemented — would agents ever use this?
- **Batch API**: Gmail supports `POST /batch` for batching multiple requests. Not implemented — no agent has needed this yet.
