"""
Capture real Gmail API responses as golden fixtures for validating our mock.

Usage:
    python scripts/capture_fixtures.py

Requires token.json from gmail_auth.py.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

TOKEN_FILE = Path(__file__).parent / "token.json"
FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "real_gmail"


def get_service():
    creds = Credentials.from_authorized_user_file(
        str(TOKEN_FILE), ["https://mail.google.com/"]
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def save(name, data):
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    if isinstance(data, dict):
        data["_captured_at"] = datetime.now(timezone.utc).isoformat()
    path = FIXTURES_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, default=str))
    print(f"  Saved {path.name}")


def capture_profile(service):
    print("\n=== Profile ===")
    profile = service.users().getProfile(userId="me").execute()
    save("profile", profile)
    return profile


def capture_labels(service):
    print("\n=== Labels ===")
    labels = service.users().labels().list(userId="me").execute()
    save("labels_list", labels)

    # Get a single label with full details
    for label in labels.get("labels", []):
        if label["id"] == "INBOX":
            inbox = service.users().labels().get(userId="me", id="INBOX").execute()
            save("label_get_inbox", inbox)
            break

    return labels


def capture_messages(service):
    print("\n=== Messages ===")

    # List messages
    msg_list = service.users().messages().list(userId="me", maxResults=10).execute()
    save("messages_list", msg_list)

    if not msg_list.get("messages"):
        print("  No messages found!")
        return None

    msg_id = msg_list["messages"][0]["id"]

    # Get message - format=full
    msg_full = service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()
    save("message_get_full", msg_full)

    # Get message - format=raw
    msg_raw = service.users().messages().get(
        userId="me", id=msg_id, format="raw"
    ).execute()
    save("message_get_raw", msg_raw)

    # Get message - format=metadata
    msg_metadata = service.users().messages().get(
        userId="me", id=msg_id, format="metadata"
    ).execute()
    save("message_get_metadata", msg_metadata)

    # Get message - format=minimal
    msg_minimal = service.users().messages().get(
        userId="me", id=msg_id, format="minimal"
    ).execute()
    save("message_get_minimal", msg_minimal)

    # List with labelIds filter
    inbox_msgs = service.users().messages().list(
        userId="me", labelIds=["INBOX"], maxResults=5
    ).execute()
    save("messages_list_inbox", inbox_msgs)

    # List with q search
    search_msgs = service.users().messages().list(
        userId="me", q="in:inbox", maxResults=5
    ).execute()
    save("messages_list_search", search_msgs)

    return msg_id


def capture_threads(service):
    print("\n=== Threads ===")

    thread_list = service.users().threads().list(userId="me", maxResults=10).execute()
    save("threads_list", thread_list)

    if not thread_list.get("threads"):
        print("  No threads found!")
        return

    thread_id = thread_list["threads"][0]["id"]

    # Get thread - format=full
    thread_full = service.users().threads().get(
        userId="me", id=thread_id, format="full"
    ).execute()
    save("thread_get_full", thread_full)

    # Get thread - format=metadata
    thread_metadata = service.users().threads().get(
        userId="me", id=thread_id, format="metadata"
    ).execute()
    save("thread_get_metadata", thread_metadata)


def capture_drafts(service):
    print("\n=== Drafts ===")

    draft_list = service.users().drafts().list(userId="me").execute()
    save("drafts_list", draft_list)

    if draft_list.get("drafts"):
        draft_id = draft_list["drafts"][0]["id"]
        draft = service.users().drafts().get(userId="me", id=draft_id).execute()
        save("draft_get", draft)


def capture_send_and_modify(service):
    print("\n=== Send + Modify ===")

    from email.mime.text import MIMEText
    import base64

    # Send a test message to self
    email = service.users().getProfile(userId="me").execute()["emailAddress"]
    msg = MIMEText("Golden fixture test message from capture script.")
    msg["To"] = email
    msg["From"] = email
    msg["Subject"] = "Mock Gmail Fixture Test"

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    save("message_send_response", sent)
    print(f"  Sent message: {sent['id']}")

    # Get the sent message in full format
    sent_full = service.users().messages().get(
        userId="me", id=sent["id"], format="full"
    ).execute()
    save("message_sent_get_full", sent_full)

    # Modify: add STARRED label
    modified = service.users().messages().modify(
        userId="me", id=sent["id"],
        body={"addLabelIds": ["STARRED"]}
    ).execute()
    save("message_modify_response", modified)

    # Trash
    trashed = service.users().messages().trash(userId="me", id=sent["id"]).execute()
    save("message_trash_response", trashed)

    # Untrash
    untrashed = service.users().messages().untrash(userId="me", id=sent["id"]).execute()
    save("message_untrash_response", untrashed)

    return sent["id"]


def capture_label_crud(service):
    print("\n=== Label CRUD ===")

    created = service.users().labels().create(
        userId="me", body={"name": "MockTestLabel", "labelListVisibility": "labelShow", "messageListVisibility": "show"}
    ).execute()
    save("label_create_response", created)

    updated = service.users().labels().update(
        userId="me", id=created["id"],
        body={"id": created["id"], "name": "MockTestLabelRenamed", "labelListVisibility": "labelShow", "messageListVisibility": "show"}
    ).execute()
    save("label_update_response", updated)

    patched = service.users().labels().patch(
        userId="me", id=created["id"],
        body={"name": "MockTestLabelPatched"}
    ).execute()
    save("label_patch_response", patched)

    service.users().labels().delete(userId="me", id=created["id"]).execute()
    print("  Deleted test label")


def capture_draft_crud(service):
    print("\n=== Draft CRUD ===")

    from email.mime.text import MIMEText
    import base64

    email = service.users().getProfile(userId="me").execute()["emailAddress"]
    msg = MIMEText("Draft fixture test.")
    msg["To"] = email
    msg["Subject"] = "Draft Fixture Test"

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    created = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    save("draft_create_response", created)

    # Get the draft
    fetched = service.users().drafts().get(userId="me", id=created["id"]).execute()
    save("draft_get_response", fetched)

    # Delete draft (cleanup)
    service.users().drafts().delete(userId="me", id=created["id"]).execute()
    print("  Deleted test draft")


def capture_history(service):
    print("\n=== History ===")

    profile = service.users().getProfile(userId="me").execute()
    history_id = str(int(profile["historyId"]) - 10)

    try:
        history = service.users().history().list(
            userId="me", startHistoryId=history_id
        ).execute()
        save("history_list", history)
    except Exception as e:
        print(f"  History error (expected if historyId too old): {e}")
        save("history_list_error", {"error": str(e)})


def capture_error_responses(service):
    print("\n=== Error Responses ===")
    from googleapiclient.errors import HttpError

    # 404: message not found
    try:
        service.users().messages().get(
            userId="me", id="nonexistent_message_id_12345", format="full"
        ).execute()
    except HttpError as e:
        error_body = json.loads(e.content.decode("utf-8"))
        save("error_message_not_found", error_body)

    # 400: invalid message send (missing raw field)
    try:
        service.users().messages().send(
            userId="me", body={}
        ).execute()
    except HttpError as e:
        error_body = json.loads(e.content.decode("utf-8"))
        save("error_invalid_message_send", error_body)


def capture_settings(service):
    print("\n=== Settings ===")

    # SendAs
    try:
        send_as = service.users().settings().sendAs().list(userId="me").execute()
        save("settings_sendas_list", send_as)
    except Exception as e:
        print(f"  SendAs error: {e}")

    # Filters
    try:
        filters = service.users().settings().filters().list(userId="me").execute()
        save("settings_filters_list", filters)
    except Exception as e:
        print(f"  Filters error: {e}")

    # Forwarding addresses
    try:
        fwd = service.users().settings().forwardingAddresses().list(userId="me").execute()
        save("settings_forwarding_list", fwd)
    except Exception as e:
        print(f"  Forwarding error: {e}")

    # Delegates
    try:
        delegates = service.users().settings().delegates().list(userId="me").execute()
        save("settings_delegates_list", delegates)
    except Exception as e:
        print(f"  Delegates error: {e}")

    # Vacation
    try:
        vacation = service.users().settings().getVacation(userId="me").execute()
        save("settings_vacation", vacation)
    except Exception as e:
        print(f"  Vacation error: {e}")

    # Auto-forwarding
    try:
        auto_fwd = service.users().settings().getAutoForwarding(userId="me").execute()
        save("settings_autoforwarding", auto_fwd)
    except Exception as e:
        print(f"  AutoForwarding error: {e}")


def main():
    print("Capturing real Gmail API responses as golden fixtures...")
    service = get_service()

    sent_msg_id = None
    created_label_id = None

    try:
        profile = capture_profile(service)
        capture_labels(service)
        msg_id = capture_messages(service)
        capture_threads(service)
        capture_drafts(service)
        sent_msg_id = capture_send_and_modify(service)
        capture_label_crud(service)
        capture_draft_crud(service)
        capture_error_responses(service)
        capture_history(service)
        capture_settings(service)

        save("_capture_metadata", {
            "account": profile["emailAddress"],
            "api_version": "v1",
            "note": "Captured from real Gmail API"
        })

        print(f"\n=== Done! Fixtures saved to {FIXTURES_DIR} ===")
        print(f"Total files: {len(list(FIXTURES_DIR.glob('*.json')))}")
    finally:
        # Verify cleanup: ensure sent test message was trashed/deleted
        if sent_msg_id:
            try:
                service.users().messages().trash(userId="me", id=sent_msg_id).execute()
            except Exception:
                pass
            # Verify it's gone from inbox
            try:
                msg = service.users().messages().get(
                    userId="me", id=sent_msg_id, format="minimal"
                ).execute()
                labels = msg.get("labelIds", [])
                if "TRASH" not in labels:
                    print(f"  WARNING: sent test message {sent_msg_id} was NOT trashed — may pollute future captures")
                else:
                    print(f"  Verified test message {sent_msg_id} is in TRASH")
            except Exception:
                print(f"  Verified test message {sent_msg_id} is deleted")


if __name__ == "__main__":
    main()
