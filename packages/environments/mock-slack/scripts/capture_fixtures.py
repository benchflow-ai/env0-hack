"""
Capture real Slack API responses as golden fixtures for validating our mock.

Usage:
    python scripts/capture_fixtures.py

Requires scripts/slack_token.json from slack_auth.py.
Bot token covers most endpoints; user token is required for search.messages.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

SCRIPTS_DIR = Path(__file__).parent
TOKEN_FILE = SCRIPTS_DIR / "slack_token.json"
FIXTURES_DIR = SCRIPTS_DIR.parent / "tests" / "fixtures" / "real_slack"

API = "https://slack.com/api"


# ---------------------------------------------------------------------------
# Auth + helpers
# ---------------------------------------------------------------------------

def load_tokens() -> dict:
    if not TOKEN_FILE.exists():
        print(f"ERROR: {TOKEN_FILE} not found. Run slack_auth.py first.")
        sys.exit(1)
    return json.loads(TOKEN_FILE.read_text())


def bot(tokens: dict) -> str:
    t = tokens.get("bot_token")
    if not t:
        print("ERROR: bot_token missing from slack_token.json")
        sys.exit(1)
    return t


def user(tokens: dict) -> str | None:
    return tokens.get("user_token")


def get(token: str, method: str, **params) -> dict:
    resp = requests.get(
        f"{API}/{method}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
    )
    resp.raise_for_status()
    return resp.json()


def post(token: str, method: str, **body) -> dict:
    resp = requests.post(
        f"{API}/{method}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
    )
    resp.raise_for_status()
    return resp.json()


def post_form(token: str, method: str, **fields) -> dict:
    """POST with application/x-www-form-urlencoded (required by some Slack endpoints)."""
    resp = requests.post(
        f"{API}/{method}",
        headers={"Authorization": f"Bearer {token}"},
        data=fields,
    )
    resp.raise_for_status()
    return resp.json()


def save(name: str, data: dict) -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    data["_captured_at"] = datetime.now(timezone.utc).isoformat()
    path = FIXTURES_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2))
    ok = data.get("ok")
    # metadata files have no "ok" field — treat as OK
    status = "OK" if (ok is True or ok is None) else "FAIL"
    print(f"  {status} {path.name}")


def check(data: dict, label: str) -> bool:
    if not data.get("ok"):
        print(f"  WARN: {label} returned ok=false: {data.get('error')}")
        return False
    return True


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------

def capture_auth(tok: str) -> dict:
    print("\n=== auth ===")
    data = get(tok, "auth.test")
    save("auth_test", data)
    return data


# ---------------------------------------------------------------------------
# team
# ---------------------------------------------------------------------------

def capture_team(tok: str) -> None:
    print("\n=== team ===")
    data = get(tok, "team.info")
    save("team_info", data)


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------

def capture_users(tok: str) -> dict:
    """Returns {user_id, email} for the first real (non-bot) user."""
    print("\n=== users ===")

    # users.list
    data = get(tok, "users.list", limit=50)
    save("users_list", data)

    # Pick first non-bot user
    members = data.get("members", [])
    real_user = next((m for m in members if not m.get("is_bot") and m["id"] != "USLACKBOT"), None)
    if not real_user:
        print("  WARN: no real user found")
        return {}

    uid = real_user["id"]
    email = real_user.get("profile", {}).get("email", "")

    # users.info
    info = get(tok, "users.info", user=uid)
    save("users_info", info)

    # users.profile.get
    profile = get(tok, "users.profile.get", user=uid)
    save("users_profile_get", profile)

    # users.getPresence
    presence = get(tok, "users.getPresence", user=uid)
    save("users_get_presence", presence)

    # users.lookupByEmail (requires users:read.email scope)
    if email:
        lookup = get(tok, "users.lookupByEmail", email=email)
        save("users_lookup_by_email", lookup)

    return {"user_id": uid, "email": email}


# ---------------------------------------------------------------------------
# conversations
# ---------------------------------------------------------------------------

def capture_conversations(tok: str, user_tok: str | None = None, human_user_id: str | None = None) -> dict:
    """Returns {channel_id, dm_channel_id, thread_ts}."""
    print("\n=== conversations ===")

    # conversations.list — public channels
    data = get(tok, "conversations.list", types="public_channel", limit=50)
    save("conversations_list", data)

    channels = data.get("channels", [])
    if not channels:
        print("  WARN: no channels found")
        return {}

    ch = channels[0]
    channel_id = ch["id"]

    # conversations.list — private channels
    # Create a temporary private channel if none exist, to capture the structure
    priv = get(tok, "conversations.list", types="private_channel", limit=20)
    if not priv.get("channels"):
        ts_priv = str(int(time.time()))[-6:]
        tmp_priv = post(tok, "conversations.create", name=f"mock-priv-{ts_priv}", is_private=True)
        if tmp_priv.get("ok"):
            priv = get(tok, "conversations.list", types="private_channel", limit=20)
            # cleanup — archive the temp private channel
            post(tok, "conversations.archive", channel=tmp_priv["channel"]["id"])
    save("conversations_list_private", priv)

    # conversations.list — DMs
    ims = get(tok, "conversations.list", types="im", limit=20)
    save("conversations_list_im", ims)

    # conversations.info
    info = get(tok, "conversations.info", channel=channel_id)
    save("conversations_info", info)

    # Find first channel with messages for non-empty history fixture
    history_channel_id = channel_id
    for scan_ch in channels:
        post(tok, "conversations.join", channel=scan_ch["id"])
        h = get(tok, "conversations.history", channel=scan_ch["id"], limit=5)
        if h.get("messages"):
            history_channel_id = scan_ch["id"]
            print(f"  Using #{scan_ch['name']} for history")
            break

    # Use history_channel_id for members/history/chat captures
    channel_id = history_channel_id

    # conversations.members
    members = get(tok, "conversations.members", channel=channel_id, limit=50)
    save("conversations_members", members)

    # conversations.history (non-empty)
    history = get(tok, "conversations.history", channel=channel_id, limit=20)
    save("conversations_history", history)

    # conversations.replies — look for threaded messages across all channels
    thread_ts = None
    # First check the current channel, then scan others
    all_channels = channels
    for scan_ch in all_channels:
        scan_history = get(tok, "conversations.history", channel=scan_ch["id"], limit=50)
        threaded = next(
            (m for m in scan_history.get("messages", []) if m.get("reply_count", 0) > 0),
            None,
        )
        if threaded:
            thread_ts = threaded["ts"]
            replies = get(tok, "conversations.replies", channel=scan_ch["id"], ts=thread_ts)
            save("conversations_replies", replies)
            print(f"  Found thread in #{scan_ch['name']} ts={thread_ts}")
            break
    if not thread_ts:
        print("  WARN: no threaded messages found — conversations_replies not captured")

    # Use a timestamp-suffixed name to avoid collisions from previous runs
    ts_suffix = str(int(time.time()))[-6:]
    # conversations.create → setPurpose → setTopic → rename → archive → unarchive → leave/join → cleanup
    created = post(tok, "conversations.create", name=f"mock-fixture-{ts_suffix}")
    save("conversations_create_response", created)
    if check(created, "conversations.create"):
        test_ch = created["channel"]["id"]

        purpose = post(tok, "conversations.setPurpose", channel=test_ch, purpose="fixture test purpose")
        save("conversations_set_purpose_response", purpose)

        topic = post(tok, "conversations.setTopic", channel=test_ch, topic="fixture test topic")
        save("conversations_set_topic_response", topic)

        renamed = post(tok, "conversations.rename", channel=test_ch, name=f"mock-fixture-{ts_suffix}-r")
        save("conversations_rename_response", renamed)

        # conversations.history on empty channel
        empty_hist = get(tok, "conversations.history", channel=test_ch, limit=10)
        save("conversations_history_empty", empty_hist)

        # conversations.invite — bot (creator, in channel) invites human user
        # conversations.kick — bot (creator) kicks human user back out
        if human_user_id:
            invited = post(tok, "conversations.invite", channel=test_ch, users=human_user_id)
            save("conversations_invite_response", invited)
            kicked = post(tok, "conversations.kick", channel=test_ch, user=human_user_id)
            save("conversations_kick_response", kicked)
        else:
            print("  SKIPPED invite/kick: no human_user_id available")

        # conversations.join (bot rejoins after being kicked)
        joined = post(tok, "conversations.join", channel=test_ch)
        save("conversations_join_response", joined)

        # conversations.leave — must happen while bot is still a member (before archive)
        left = post(tok, "conversations.leave", channel=test_ch)
        save("conversations_leave_response", left)

        # Re-join so bot can archive
        post(tok, "conversations.join", channel=test_ch)

        # conversations.archive — removes bot from channel as a side-effect
        archived = post(tok, "conversations.archive", channel=test_ch)
        save("conversations_archive_response", archived)

        # conversations.unarchive — use user token (admin scope) since bot was removed by archive
        unarchive_tok = user_tok or tok
        unarchived = post(unarchive_tok, "conversations.unarchive", channel=test_ch)
        save("conversations_unarchive_response", unarchived)

        # cleanup: bot re-joins and re-archives
        post(tok, "conversations.join", channel=test_ch)
        post(tok, "conversations.archive", channel=test_ch)
        print(f"  Cleaned up test channel {test_ch}")

    # --- Error responses ---
    # conversations.info with invalid channel
    err_info = get(tok, "conversations.info", channel="C000INVALID")
    save("conversations_info_error_channel_not_found", err_info)

    # conversations.history with invalid channel
    err_hist = get(tok, "conversations.history", channel="C000INVALID", limit=1)
    save("conversations_history_error_channel_not_found", err_hist)

    return {"channel_id": channel_id, "thread_ts": thread_ts}


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------

def capture_chat(tok: str, channel_id: str) -> dict:
    """Returns {ts} for the posted message."""
    print("\n=== chat ===")

    # chat.postMessage
    posted = post(tok, "chat.postMessage", channel=channel_id, text="Mock fixture capture test message")
    save("chat_post_message_response", posted)
    if not check(posted, "chat.postMessage"):
        return {}

    ts = posted["ts"]

    # chat.getPermalink
    permalink = get(tok, "chat.getPermalink", channel=channel_id, message_ts=ts)
    save("chat_get_permalink", permalink)

    # chat.postEphemeral (to self — requires users:read to get a user_id)
    auth_info = get(tok, "auth.test")
    bot_user_id = auth_info.get("user_id", "")
    if bot_user_id:
        ephemeral = post(tok, "chat.postEphemeral",
                         channel=channel_id, user=bot_user_id, text="ephemeral fixture test")
        save("chat_post_ephemeral_response", ephemeral)

    # chat.update
    updated = post(tok, "chat.update", channel=channel_id, ts=ts, text="Mock fixture capture test message (edited)")
    save("chat_update_response", updated)

    # post a reply (thread)
    reply = post(tok, "chat.postMessage", channel=channel_id, thread_ts=ts, text="This is a thread reply")
    save("chat_post_message_reply_response", reply)

    # chat.delete the reply (cleanup)
    if check(reply, "chat.postMessage (reply)"):
        post(tok, "chat.delete", channel=channel_id, ts=reply["ts"])

    # chat.delete the parent (cleanup)
    deleted = post(tok, "chat.delete", channel=channel_id, ts=ts)
    save("chat_delete_response", deleted)
    print(f"  Cleaned up test message {ts}")

    # --- Error responses ---
    # chat.postMessage with invalid channel
    err_post = post(tok, "chat.postMessage", channel="C000INVALID", text="should fail")
    save("chat_post_message_error_channel_not_found", err_post)

    # chat.postMessage with missing text/blocks/attachments
    err_no_text = post(tok, "chat.postMessage", channel=channel_id)
    save("chat_post_message_error_no_text", err_no_text)

    # chat.update with invalid ts
    err_update = post(tok, "chat.update", channel=channel_id, ts="0000000000.000000", text="nope")
    save("chat_update_error_message_not_found", err_update)

    # chat.delete with invalid ts
    err_delete = post(tok, "chat.delete", channel=channel_id, ts="0000000000.000000")
    save("chat_delete_error_message_not_found", err_delete)

    return {"ts": ts}


# ---------------------------------------------------------------------------
# reactions
# ---------------------------------------------------------------------------

def capture_reactions(tok: str, channel_id: str) -> None:
    print("\n=== reactions ===")

    # Post a message to react to
    msg = post(tok, "chat.postMessage", channel=channel_id, text="Reaction fixture test")
    if not check(msg, "chat.postMessage for reactions"):
        return

    ts = msg["ts"]

    # reactions.add
    added = post(tok, "reactions.add", channel=channel_id, timestamp=ts, name="thumbsup")
    save("reactions_add_response", added)

    # reactions.get (with reaction)
    got = get(tok, "reactions.get", channel=channel_id, timestamp=ts)
    save("reactions_get", got)

    # reactions.remove
    removed = post(tok, "reactions.remove", channel=channel_id, timestamp=ts, name="thumbsup")
    save("reactions_remove_response", removed)

    # reactions.get (empty — no reactions)
    got_empty = get(tok, "reactions.get", channel=channel_id, timestamp=ts)
    save("reactions_get_empty", got_empty)

    # --- Error responses ---
    # reactions.add with invalid channel/ts
    err_react = post(tok, "reactions.add", channel="C000INVALID", timestamp="0000000000.000000", name="thumbsup")
    save("reactions_add_error_invalid_target", err_react)

    # cleanup
    post(tok, "chat.delete", channel=channel_id, ts=ts)


# ---------------------------------------------------------------------------
# pins
# ---------------------------------------------------------------------------

def capture_pins(tok: str, channel_id: str) -> None:
    print("\n=== pins ===")

    # Post a message to pin
    msg = post(tok, "chat.postMessage", channel=channel_id, text="Pin fixture test")
    if not check(msg, "chat.postMessage for pins"):
        return

    ts = msg["ts"]

    # pins.add
    added = post(tok, "pins.add", channel=channel_id, timestamp=ts)
    save("pins_add_response", added)

    # pins.list (with item)
    lst = get(tok, "pins.list", channel=channel_id)
    save("pins_list", lst)

    # pins.remove
    removed = post(tok, "pins.remove", channel=channel_id, timestamp=ts)
    save("pins_remove_response", removed)

    # pins.list (empty)
    lst_empty = get(tok, "pins.list", channel=channel_id)
    save("pins_list_empty", lst_empty)

    # cleanup
    post(tok, "chat.delete", channel=channel_id, ts=ts)


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------

def capture_files(tok: str, channel_id: str) -> None:
    print("\n=== files ===")

    # files.list captured after upload (see below)

    # New Slack upload flow (files.upload deprecated March 2025):
    # Step 1: get upload URL (requires form encoding, not JSON)
    content = "Hello from capture_fixtures.py"
    content_bytes = content.encode("utf-8")
    url_resp = post_form(tok, "files.getUploadURLExternal",
                         filename="fixture_test.txt",
                         length=len(content_bytes))
    if not check(url_resp, "files.getUploadURLExternal"):
        return

    upload_url = url_resp["upload_url"]
    file_id = url_resp["file_id"]

    # Step 2: PUT content to upload URL
    put_resp = requests.post(
        upload_url,
        headers={"Authorization": f"Bearer {tok}"},
        files={"file": ("fixture_test.txt", content_bytes, "text/plain")},
    )
    put_resp.raise_for_status()

    # Step 3: complete the upload (share to channel)
    complete_resp = post(tok, "files.completeUploadExternal",
                         files=[{"id": file_id, "title": "Fixture Test File"}],
                         channel_id=channel_id)
    # completeUploadExternal returns {"ok": true, "files": [...]}
    if complete_resp.get("ok") and complete_resp.get("files"):
        upload_result = {"ok": True, "file": complete_resp["files"][0]}
    else:
        upload_result = complete_resp
    save("files_upload_response", upload_result)

    if not check(upload_result, "files.upload (new flow)"):
        return

    # files.info
    info = get(tok, "files.info", file=file_id)
    save("files_info", info)

    # files.list — captured while file still exists
    lst = get(tok, "files.list", count=10)
    save("files_list", lst)

    # files.list filtered by channel — captured while file still exists
    lst_ch = get(tok, "files.list", channel=channel_id, count=10)
    save("files_list_by_channel", lst_ch)

    # files.delete (cleanup)
    deleted = post(tok, "files.delete", file=file_id)
    save("files_delete_response", deleted)
    print(f"  Cleaned up test file {file_id}")


# ---------------------------------------------------------------------------
# search (user token required)
# ---------------------------------------------------------------------------

def capture_search(user_tok: str | None) -> None:
    print("\n=== search ===")
    if not user_tok:
        print("  SKIPPED: no user_token in slack_token.json (search.* requires user token)")
        return

    data = get(user_tok, "search.messages", query="Edge Account Review Progress", count=10)
    save("search_messages", data)

    # Empty search
    empty = get(user_tok, "search.messages", query="zzzzzzzzzzzzzzzznomatch99999", count=5)
    save("search_messages_empty", empty)


# ---------------------------------------------------------------------------
# reminders (user token preferred)
# ---------------------------------------------------------------------------

def capture_reminders(bot_tok: str, user_tok: str | None) -> None:
    print("\n=== reminders ===")
    tok = user_tok or bot_tok

    # Create a temporary reminder so list is non-empty
    future_ts = int(time.time()) + 3600  # 1 hour from now
    created = post(tok, "reminders.add", text="fixture capture test reminder", time=future_ts)
    reminder_id = created.get("reminder", {}).get("id") if created.get("ok") else None

    data = get(tok, "reminders.list")
    save("reminders_list", data)

    # cleanup
    if reminder_id:
        post(tok, "reminders.delete", reminder=reminder_id)


# ---------------------------------------------------------------------------
# users mutations (profile.set, setPresence) — best-effort
# ---------------------------------------------------------------------------

def capture_user_mutations(bot_tok: str, user_tok: str | None) -> None:
    print("\n=== users mutations ===")

    # users.setPresence (bot token)
    presence_set = post(bot_tok, "users.setPresence", presence="auto")
    save("users_set_presence_response", presence_set)

    # users.profile.set requires user token (not_allowed_token_type with bot token)
    if not user_tok:
        print("  SKIPPED users.profile.set: no user_token in slack_token.json")
        return

    profile_set = post(user_tok, "users.profile.set",
                       profile={"status_text": "capturing fixtures", "status_emoji": ":camera:"})
    save("users_profile_set_response", profile_set)

    # Reset status
    post(user_tok, "users.profile.set", profile={"status_text": "", "status_emoji": ""})
    print("  Reset status after capture")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Capturing real Slack API responses as golden fixtures...")
    tokens = load_tokens()
    bot_tok = bot(tokens)
    user_tok = user(tokens)

    # auth + team
    auth_info = capture_auth(bot_tok)
    capture_team(bot_tok)

    # users
    user_info = capture_users(bot_tok)

    # conversations — get a real channel to work with
    conv_info = capture_conversations(bot_tok, user_tok, human_user_id=user_info.get("user_id"))
    channel_id = conv_info.get("channel_id")

    if not channel_id:
        print("\nERROR: no channel_id available — skipping chat/reactions/pins/files")
    else:
        capture_chat(bot_tok, channel_id)
        capture_reactions(bot_tok, channel_id)
        capture_pins(bot_tok, channel_id)
        capture_files(bot_tok, channel_id)

    # search (user token)
    capture_search(user_tok)

    # reminders
    capture_reminders(bot_tok, user_tok)

    # user mutations
    capture_user_mutations(bot_tok, user_tok)

    # metadata
    save("_capture_metadata", {
        "team": auth_info.get("team", ""),
        "team_id": auth_info.get("team_id", ""),
        "bot_user": auth_info.get("user", ""),
        "bot_user_id": auth_info.get("user_id", ""),
        "api_base": API,
        "auth_method": "bot token (xoxb) + user token (xoxp) for search",
        "capture_script": "scripts/capture_fixtures.py",
        "note": "Test workspace. User token used for search.messages only.",
    })

    fixtures = list(FIXTURES_DIR.glob("*.json"))
    print(f"\n=== Done! {len(fixtures)} fixtures in {FIXTURES_DIR} ===")

    # Coverage summary
    expected = {
        "auth_test", "team_info",
        "users_list", "users_info", "users_profile_get", "users_get_presence",
        "users_lookup_by_email", "users_set_presence_response", "users_profile_set_response",
        "conversations_list", "conversations_list_private", "conversations_list_im",
        "conversations_info", "conversations_members",
        "conversations_history", "conversations_history_empty",
        "conversations_replies",
        "conversations_create_response", "conversations_rename_response",
        "conversations_archive_response", "conversations_unarchive_response",
        "conversations_join_response", "conversations_leave_response",
        "conversations_invite_response", "conversations_kick_response",
        "conversations_set_purpose_response", "conversations_set_topic_response",
        "chat_post_message_response", "chat_post_message_reply_response",
        "chat_post_ephemeral_response", "chat_update_response",
        "chat_delete_response", "chat_get_permalink",
        "reactions_add_response", "reactions_remove_response",
        "reactions_get", "reactions_get_empty",
        "pins_add_response", "pins_remove_response", "pins_list", "pins_list_empty",
        "files_upload_response", "files_info", "files_list",
        "files_list_by_channel", "files_delete_response",
        "search_messages", "search_messages_empty",
        "reminders_list",
        # error fixtures
        "conversations_info_error_channel_not_found",
        "conversations_history_error_channel_not_found",
        "chat_post_message_error_channel_not_found",
        "chat_post_message_error_no_text",
        "chat_update_error_message_not_found",
        "chat_delete_error_message_not_found",
        "reactions_add_error_invalid_target",
    }
    captured = {p.stem for p in fixtures if not p.stem.startswith("_")}
    missing = expected - captured
    if missing:
        print(f"\nMissing fixtures ({len(missing)}):")
        for name in sorted(missing):
            print(f"  - {name}.json")
    else:
        print("All expected fixtures captured.")


if __name__ == "__main__":
    main()
