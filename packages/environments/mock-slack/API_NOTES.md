# Mock Slack API Notes

## Ground Truth

- **Official API reference**: [api.slack.com/methods](https://api.slack.com/methods)
- **OpenAPI spec** (machine-readable schema): [slackapi/slack-api-specs](https://github.com/slackapi/slack-api-specs) — `web-api/slack_web_openapi_v2.json` (covers all methods with request params, response schemas, error codes). Note: Slack has no Discovery Document equivalent; this GitHub repo is the closest analog.
- **Rate limit tiers**: [api.slack.com/docs/rate-limits](https://api.slack.com/docs/rate-limits)
- **Block Kit reference**: [api.slack.com/block-kit](https://api.slack.com/block-kit)
- **Real workspace**: Slack Developer Program sandbox (`SLACK_BOT_TOKEN` bot token, `SLACK_USER_TOKEN` user token in env)
- **Auth script**: `scripts/slack_auth.py`
- **Fixture capture**: `scripts/capture_fixtures.py` → `tests/fixtures/real_slack/`
- **Endpoint spec**: `tests/fixtures/slack_api_spec.json`
- **Coverage map**: `tests/fixtures/mock_coverage.json`

### Reference Implementations

- **slack-machine** (github.com/DonJayamanne/slack-machine): Production Slack bot framework, real API usage patterns for 20+ methods
- **python-slack-sdk** (github.com/slackapi/python-slack-sdk): Official SDK — WebClient source shows exact request/response shapes for all methods
- **slack-export-viewer** (github.com/hfaran/slack-export-viewer): Real exported Slack JSON shows channel/message/user schema in practice

---

## API Quirks (append-only, dated)

Discovered during golden fixture analysis on 2026-03-18. Each finding references a fixture in `tests/fixtures/real_slack/`.

- **2026-03-18: All responses are HTTP 200, including errors.** Slack never returns 4xx/5xx for application-level errors — `ok: false` errors use HTTP 200 just like successes. Only auth failures (401) and rate limits (429) use non-200 status. See any `*_response.json`.

- **2026-03-18: Timestamps are epoch seconds as decimal strings.** Format: `"1234567890.123456"` — not integers, not ISO 8601. Microsecond precision. Used in `ts`, `thread_ts`, `latest`, `oldest` params. See `conversations_history.json`.

- **2026-03-18: `warning: "missing_charset"` appears on all bot-token write responses.** Every POST endpoint that modifies state returns `warning` and `response_metadata.warnings: ["missing_charset"]`. Read-only endpoints do not. See `chat_delete_response.json`, `conversations_leave_response.json`.

- **2026-03-18: `conversations.leave` has two distinct error shapes.** Standard errors use `{"ok": false, "error": "..."}`. But leaving a channel you were never in returns `{"ok": false, "not_in_channel": true}` — the `error` key is absent. This format is unique to this endpoint. See Slack docs (no fixture captured for this case).

- **2026-03-18: `conversations.leave` on general channel returns `cant_leave_general`.** The channel named "general" (default workspace channel) cannot be left by any user. See Slack docs.

- **2026-03-18: `conversations.info` does NOT return `num_members`.** Only `conversations.list` includes `num_members`. To count members, use `conversations.members`. See `conversations_info.json` vs `conversations_list.json`.

- **2026-03-18: Thread reply messages do not appear in `conversations.history`.** History returns only top-level messages (and thread parents). Replies are accessible only via `conversations.replies`. See `conversations_history.json`, `conversations_replies.json`.

- **2026-03-18: `conversations.replies` returns the parent as index 0.** The thread root is always first. Replies follow in chronological order. Parent carries `is_locked`, `subscribed`, `reply_users`, `reply_users_count`, `latest_reply`. Replies carry `parent_user_id`. See `conversations_replies.json`.

- **2026-03-18: IM channels have a completely different schema from public channels.** Key IM fields: `user` (other party's ID), `is_user_deleted`, `priority` (float). Fields absent in IM: `name`, `topic`, `purpose`, `creator`, `num_members`. See `conversations_list_im.json`.

- **2026-03-18: `USLACKBOT` (Slackbot) has `is_bot: false`.** Despite being a system automation user, it is not classified as a bot by the API. It also has `always_active: true` in its profile. See `users_list.json`.

- **2026-03-18: `parent_conversation` field serializes as explicit `null`, not absent.** Channel objects always include `"parent_conversation": null` even though no value is set. This is one of the very few nullable fields that Slack keeps present (not omits). See `conversations_info.json`.

- **2026-03-18: Message `blocks` is always present, even for plain-text messages.** Every non-empty message has a `blocks` array containing at least one `rich_text` block. The block structure has: `type`, `block_id`, `elements` (array of `rich_text_section`). See `conversations_history.json`.

- **2026-03-18: Pagination uses opaque cursor strings, not page numbers.** Pass `cursor` from `response_metadata.next_cursor`. Empty string means no more pages. Applies to: `conversations.list`, `conversations.members`, `conversations.history`, `conversations.replies`, `users.list`, `reactions.list`, `files.list`. See `conversations_list.json`.

- **2026-03-18: Rate limit responses use HTTP 429 with `Retry-After` header.** Body: `{"ok": false, "error": "ratelimited"}`. Header: `Retry-After: <seconds>`. Methods have tiers (1/2/3/4/Special) from 1 req/min (Tier 1) to 100/min (Tier 4). `chat.postMessage` is Special: 1/sec per channel. See [rate limits docs](https://api.slack.com/docs/rate-limits).

- **2026-03-18: `files.upload` v1 (multipart form) is deprecated since 2024.** New SDK versions use v2: `files.getUploadURLExternal` + `files.completeUploadExternal`. The real API still accepts v1 but warns. See `files_upload_response.json`.

---

## Intentionally Skipped

Features consciously excluded from the mock. Per-endpoint skip reasons are in `tests/fixtures/mock_coverage.json`.

| Feature | Reason |
|---------|--------|
| Rate limit enforcement | Not relevant for mock — agents shouldn't need to handle backoff in test environments |
| `files.upload` v2 (`getUploadURLExternal` + `completeUploadExternal`) | v1 still accepted by real API; two-step v2 flow adds complexity with no agent-testing benefit |
| `chat.scheduleMessage` / `chat.deleteScheduledMessage` | Scheduled delivery timing is meaningless in a mock with no real clock |
| `chat.unfurl` | Requires fetching external URLs; out of scope for a self-contained mock |
| DnD (`dnd.*`) | Do Not Disturb is a notification preference, not a communication primitive — no agent task exercises it |
| Stars / Saved Items (`stars.*`) | Deprecated by Slack in 2023 in favor of Saved Items; not worth implementing a deprecated API |
| Usergroups (`usergroups.*`) | User group @-mention routing not needed for current agent task coverage |
| `team.accessLogs` / `team.billableInfo` | Admin-only analytics; not relevant to agent workflow testing |
| WebSocket / RTM API | Real-time push not needed; mock is synchronous REST only |
| OAuth flow | Mock uses static `X-Workspace-ID` header identity; no token validation needed for agent testing |
| Block Kit interactive elements | Agents read block content; they don't invoke buttons, modals, or input blocks |

---

## Key Design Choices

- **Stateful mock, not replay**: Full CRUD with persistent SQLite — state changes from one API call affect subsequent calls, enabling multi-step agent workflows like channel create → invite → post → archive.

- **Single-workspace, token-agnostic**: All requests resolve to one workspace via `X-Workspace-ID` header. No real token parsing or OAuth — agents can use any string as a token. Diverges from real Slack (multi-workspace, bot-scoped tokens) but simplifies agent testing.

- **`ok: true/false` always HTTP 200**: Matches real Slack — all application errors are in the body, never in HTTP status. This is the opposite of mock-gmail, which uses proper HTTP 4xx codes. Agents using a Slack SDK will expect body-level error codes, not HTTP exceptions.

- **`_slack_error()` helper**: All error paths use `{"ok": false, "error": "snake_case_code"}`. The error code strings match real Slack exactly (e.g., `channel_not_found`, `cant_leave_general`, `already_archived`) so agents doing error-code matching work correctly.

- **`conversations.leave` `not_in_channel` special case**: Returns `{"ok": false, "not_in_channel": true}` with no `error` key, matching the real API's non-standard shape for this specific condition.

- **`exclude_none` on `MessageSchema`**: Real Slack omits null fields entirely rather than serializing them as `null`. Mock uses a custom `model_serializer` instead of Pydantic's `model_config = ConfigDict(exclude_none=True)` because the channel schema needs `parent_conversation: null` to be explicitly present — the one field that real Slack always includes as null.

- **`_channel_to_schema` vs `_channel_to_schema_list`**: The `conversations.info` response does not include `num_members`; `conversations.list` does. Two separate serializer helpers enforce this shape difference, which is a real Slack API quirk verified against fixtures.

- **`IMChannelSchema` entirely separate from `ChannelSchema`**: DM channels have no `name`, `topic`, `purpose`, or `creator`. Separate schemas are cleaner than a single schema with conditionals and match real Slack's divergent shapes.

- **Thread reply fields only in `conversations.replies`**: `is_locked`, `subscribed`, `reply_users`, `latest_reply` appear on the parent (index 0); `parent_user_id` appears on replies. These fields are absent in `conversations.history`, matching real Slack behavior.

---

## Open Questions

- **`files.upload` v2**: Slack deprecated v1 in 2024. Official SDKs now use `getUploadURLExternal` + `completeUploadExternal`. Should mock implement v2? Relevant if agents use an up-to-date Slack SDK that has dropped v1 support.

- **`conversations.open`**: Currently returns a minimal channel object but does not persist a new IM channel in state. Should it create a real IM channel? Agents that open a DM and then try to fetch its history would silently get an empty result.

- **Block Kit fidelity**: Mock returns a fixed minimal `rich_text` block for every message. Real Slack messages have varied block types (`section`, `divider`, `image`, `context`). Do agents ever branch on `block.type` or inspect `block_id`?

- **Search ranking**: `search.messages` returns results in insertion order. Real Slack ranks by relevance score and recency. Would an agent fail a task because it expected the most relevant result first?

- **Rate limit simulation**: If added, should it be opt-in via a request header (`X-Mock-Rate-Limit: true`) so specific tests can verify agent retry/backoff behavior without slowing the entire test suite?

- **Error response fixtures**: `tests/fixtures/real_slack/` currently captures only success responses. Per the API Validation Playbook, error response fixtures should also be captured to validate mock error shapes match real Slack — the `not_in_channel` special case was discovered from docs, not a fixture.
