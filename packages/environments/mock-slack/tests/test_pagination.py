"""Pagination tests for cursor-based endpoints.

Verifies that conversations.history, conversations.replies,
conversations.list, conversations.members, and users.list
all return correct cursors and can be iterated to exhaustion.
"""

import base64

import pytest

WORKSPACE_HEADER = {"X-Mock-Slack-Workspace": "workspace_001"}

# Channel with known seeded messages
CHANNEL_GENERAL = "C01GENERAL"
CHANNEL_ENGINEERING = "C03ENGINEERING"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decode_cursor(cursor: str) -> str:
    return base64.b64decode(cursor.encode()).decode()


def _paginate(client, method: str, url: str, result_key: str, page_size: int, **extra_params):
    """Collect all items by following cursors. Returns (all_items, page_count)."""
    items = []
    pages = 0
    cursor = None
    while True:
        params = {**extra_params, "limit": page_size}
        if cursor:
            params["cursor"] = cursor
        resp = client.request(method, url, params=params, headers=WORKSPACE_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"], f"API error: {data}"
        batch = data[result_key]
        items.extend(batch)
        pages += 1
        meta = data.get("response_metadata", {})
        cursor = meta.get("next_cursor", "")
        if not cursor:
            break
    return items, pages


# ---------------------------------------------------------------------------
# conversations.history
# ---------------------------------------------------------------------------

class TestHistoryPagination:
    def test_no_pagination_needed(self, client):
        """When total messages fit in one page, next_cursor is empty."""
        # CHANNEL_GENERAL has ~5 seeded messages; limit=20 (max) should cover all.
        resp = client.get(
            f"/api/conversations.history?channel={CHANNEL_GENERAL}&limit=20",
            headers=WORKSPACE_HEADER,
        ).json()
        assert resp["ok"]
        assert not resp["has_more"]
        assert "response_metadata" not in resp

    def test_cursor_present_when_has_more(self, client):
        """Small limit triggers has_more and a non-empty cursor."""
        resp = client.get(
            f"/api/conversations.history?channel={CHANNEL_GENERAL}&limit=1",
            headers=WORKSPACE_HEADER,
        ).json()
        assert resp["ok"]
        assert resp["has_more"]
        cursor = resp["response_metadata"]["next_cursor"]
        assert cursor, "expected non-empty cursor when has_more=true"

    def test_history_limit_clamped_at_100(self, client):
        """Requests above Slack's page cap should still return at most 100 messages."""
        for idx in range(105):
            post = client.post(
                "/api/chat.postMessage",
                headers=WORKSPACE_HEADER,
                json={"channel": CHANNEL_GENERAL, "text": f"clamp probe {idx}"},
            ).json()
            assert post["ok"]

        resp = client.get(
            f"/api/conversations.history?channel={CHANNEL_GENERAL}&limit=1000",
            headers=WORKSPACE_HEADER,
        ).json()
        assert resp["ok"]
        assert len(resp["messages"]) == 100
        assert resp["has_more"]
        assert resp["response_metadata"]["next_cursor"]

    def test_cursor_format(self, client):
        """Cursor decodes to 'next_ts:<ts>' matching real Slack format."""
        resp = client.get(
            f"/api/conversations.history?channel={CHANNEL_GENERAL}&limit=1",
            headers=WORKSPACE_HEADER,
        ).json()
        cursor = resp["response_metadata"]["next_cursor"]
        payload = _decode_cursor(cursor)
        assert payload.startswith("next_ts:"), f"unexpected payload: {payload}"
        ts = payload[len("next_ts:"):]
        assert ts, "ts part of cursor should not be empty"

    def test_paginate_all_messages(self, client):
        """Iterating with cursor collects all messages without duplicates."""
        all_full, _ = _paginate(
            client, "GET", "/api/conversations.history", "messages", 20,
            channel=CHANNEL_GENERAL,
        )
        all_paged, pages = _paginate(
            client, "GET", "/api/conversations.history", "messages", 2,
            channel=CHANNEL_GENERAL,
        )
        ts_full = [m["ts"] for m in all_full]
        ts_paged = [m["ts"] for m in all_paged]
        assert sorted(ts_full) == sorted(ts_paged), "paginated results differ from full fetch"
        assert len(set(ts_paged)) == len(ts_paged), "duplicate messages in paginated results"
        if len(all_full) > 2:
            assert pages > 1, "expected multiple pages"

    def test_messages_newest_first_across_pages(self, client):
        """Messages are returned newest-first across page boundaries."""
        all_msgs, _ = _paginate(
            client, "GET", "/api/conversations.history", "messages", 2,
            channel=CHANNEL_GENERAL,
        )
        timestamps = [float(m["ts"]) for m in all_msgs]
        assert timestamps == sorted(timestamps, reverse=True), "messages not in newest-first order"

    def test_cursor_ignores_oldest_param(self, client):
        """When cursor is provided, oldest param is ignored (cursor takes precedence)."""
        page1 = client.get(
            f"/api/conversations.history?channel={CHANNEL_GENERAL}&limit=1",
            headers=WORKSPACE_HEADER,
        ).json()
        cursor = page1["response_metadata"]["next_cursor"]
        if not cursor:
            pytest.skip("not enough messages to paginate")

        # Pass an oldest equal to page 1's newest message. If oldest is applied
        # after the cursor, it conflicts with "older than cursor" and returns no page.
        oldest = page1["messages"][0]["ts"]
        resp = client.get(
            f"/api/conversations.history?channel={CHANNEL_GENERAL}&limit=1"
            f"&cursor={cursor}&oldest={oldest}",
            headers=WORKSPACE_HEADER,
        ).json()
        assert resp["ok"]
        assert resp["messages"]
        # The page returned via cursor must be older than the first page
        assert float(resp["messages"][0]["ts"]) < float(page1["messages"][0]["ts"])


# ---------------------------------------------------------------------------
# conversations.replies
# ---------------------------------------------------------------------------

class TestRepliesPagination:
    def _get_threaded_ts(self, client):
        """Find a message that has replies."""
        resp = client.get(
            f"/api/conversations.history?channel={CHANNEL_ENGINEERING}&limit=100",
            headers=WORKSPACE_HEADER,
        ).json()
        for msg in resp.get("messages", []):
            if msg.get("reply_count", 0) > 0:
                return msg["ts"]
        return None

    def test_paginate_replies(self, client):
        """Replies can be paginated with cursor."""
        ts = self._get_threaded_ts(client)
        if not ts:
            pytest.skip("no threaded messages in seed data")

        all_full, _ = _paginate(
            client, "GET", "/api/conversations.replies", "messages", 1000,
            channel=CHANNEL_ENGINEERING, ts=ts,
        )
        all_paged, pages = _paginate(
            client, "GET", "/api/conversations.replies", "messages", 2,
            channel=CHANNEL_ENGINEERING, ts=ts,
        )
        ts_full = sorted(m["ts"] for m in all_full)
        ts_paged = sorted(m["ts"] for m in all_paged)
        assert ts_full == ts_paged

    def test_replies_cursor_format(self, client):
        """Reply cursor decodes to 'next_ts:<ts>'."""
        ts = self._get_threaded_ts(client)
        if not ts:
            pytest.skip("no threaded messages in seed data")

        resp = client.get(
            f"/api/conversations.replies?channel={CHANNEL_ENGINEERING}&ts={ts}&limit=1",
            headers=WORKSPACE_HEADER,
        ).json()
        cursor = resp.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            pytest.skip("not enough replies to paginate")
        payload = _decode_cursor(cursor)
        assert payload.startswith("next_ts:")


# ---------------------------------------------------------------------------
# conversations.list
# ---------------------------------------------------------------------------

class TestListPagination:
    def test_no_pagination_needed(self, client):
        resp = client.get(
            "/api/conversations.list?limit=1000",
            headers=WORKSPACE_HEADER,
        ).json()
        assert resp["ok"]
        assert resp["response_metadata"]["next_cursor"] == ""

    def test_cursor_present_when_has_more(self, client):
        resp = client.get(
            "/api/conversations.list?limit=1",
            headers=WORKSPACE_HEADER,
        ).json()
        assert resp["ok"]
        cursor = resp["response_metadata"]["next_cursor"]
        assert cursor, "expected cursor when more channels exist"

    def test_cursor_format(self, client):
        resp = client.get(
            "/api/conversations.list?limit=1",
            headers=WORKSPACE_HEADER,
        ).json()
        cursor = resp["response_metadata"]["next_cursor"]
        if not cursor:
            pytest.skip("only one channel in workspace")
        payload = _decode_cursor(cursor)
        assert payload.startswith("after:")

    def test_paginate_all_channels(self, client):
        all_full, _ = _paginate(
            client, "GET", "/api/conversations.list", "channels", 1000,
        )
        all_paged, pages = _paginate(
            client, "GET", "/api/conversations.list", "channels", 2,
        )
        ids_full = sorted(c["id"] for c in all_full)
        ids_paged = sorted(c["id"] for c in all_paged)
        assert ids_full == ids_paged, "paginated list differs from full fetch"
        assert len(set(ids_paged)) == len(ids_paged), "duplicate channels in paginated results"

    def test_no_duplicates_across_pages(self, client):
        all_paged, _ = _paginate(
            client, "GET", "/api/conversations.list", "channels", 3,
        )
        ids = [c["id"] for c in all_paged]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# conversations.members
# ---------------------------------------------------------------------------

class TestMembersPagination:
    def test_paginate_members(self, client):
        all_full, _ = _paginate(
            client, "GET", "/api/conversations.members", "members", 1000,
            channel=CHANNEL_GENERAL,
        )
        all_paged, _ = _paginate(
            client, "GET", "/api/conversations.members", "members", 2,
            channel=CHANNEL_GENERAL,
        )
        assert sorted(all_full) == sorted(all_paged)
        assert len(set(all_paged)) == len(all_paged), "duplicate members in paginated results"

    def test_cursor_format(self, client):
        resp = client.get(
            f"/api/conversations.members?channel={CHANNEL_GENERAL}&limit=1",
            headers=WORKSPACE_HEADER,
        ).json()
        cursor = resp.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            pytest.skip("only one member in channel")
        payload = _decode_cursor(cursor)
        assert payload.startswith("after:")


# ---------------------------------------------------------------------------
# users.list
# ---------------------------------------------------------------------------

class TestUsersListPagination:
    def test_no_pagination_needed(self, client):
        resp = client.get(
            "/api/users.list?limit=1000",
            headers=WORKSPACE_HEADER,
        ).json()
        assert resp["ok"]
        assert resp["response_metadata"]["next_cursor"] == ""

    def test_cursor_present_when_has_more(self, client):
        resp = client.get(
            "/api/users.list?limit=1",
            headers=WORKSPACE_HEADER,
        ).json()
        assert resp["ok"]
        cursor = resp["response_metadata"]["next_cursor"]
        assert cursor, "expected cursor when more users exist"

    def test_paginate_all_users(self, client):
        all_full, _ = _paginate(
            client, "GET", "/api/users.list", "members", 1000,
        )
        all_paged, pages = _paginate(
            client, "GET", "/api/users.list", "members", 2,
        )
        ids_full = sorted(u["id"] for u in all_full)
        ids_paged = sorted(u["id"] for u in all_paged)
        assert ids_full == ids_paged
        assert len(set(ids_paged)) == len(ids_paged), "duplicate users in paginated results"
        if len(all_full) > 2:
            assert pages > 1

    def test_cursor_format(self, client):
        resp = client.get(
            "/api/users.list?limit=1",
            headers=WORKSPACE_HEADER,
        ).json()
        cursor = resp["response_metadata"]["next_cursor"]
        assert cursor
        payload = _decode_cursor(cursor)
        assert payload.startswith("after:")
